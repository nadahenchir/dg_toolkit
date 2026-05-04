import logging

logger = logging.getLogger(__name__)


def _build_maturity_path(from_level: int, to_level: int, target_level: int) -> str | None:
    """
    Builds a human-readable incremental path from current action step to target.

    Example: from_level=1, to_level=2, target_level=4
    → "L1→L2, then L2→L3, then L3→L4"

    Returns None if any argument is missing or if to_level already reaches target.
    """
    if from_level is None or to_level is None or target_level is None:
        return None
    if to_level >= target_level:
        # This action already reaches the target — no further steps to describe
        return None

    steps = [f"L{from_level}→L{to_level}"]
    level = to_level
    while level < target_level:
        steps.append(f"L{level}→L{level + 1}")
        level += 1
    return ", then ".join(steps)


def build_prompt(
    kpi_name: str,
    action_text: str,
    org_context: dict,
    retrieved_chunks: list[dict],
    similar_orgs: list[dict] = None
) -> list[dict]:
    """
    Builds the messages array for the OpenAI chat completion API.

    Gap convention (matches DB):
        gap = target_level - maturity_level
        gap > 0  → below target (needs improvement)
        gap == 0 → on target (sustain)
        gap < 0  → above target (leverage strength)

    Narrative structure:
        Paragraph 1 — Current standing: describe where the organization is today
                      on this specific KPI, what that level means in practice,
                      and whether they are below, at, or above their target.
        Paragraph 2 — Action in context: explain the recommended action tailored
                      to the organization, their industry, and their gap.
                      When below target, reference the incremental improvement path
                      (e.g. L1→L2, then L2→L3, then L3→L4) and why this step comes first.
                      End with 1-2 sentences on what similar organizations achieved
                      with this action (if data is available).
    """

    # ── Format retrieved chunks ──────────────────────────────────────────────
    if retrieved_chunks:
        chunks_text = "\n\n".join([
            f"Reference {i+1}:\n{chunk['chunk_text']}"
            for i, chunk in enumerate(retrieved_chunks)
        ])
    else:
        chunks_text = "No additional reference material available."

    org_name     = org_context.get("org_name", "the organization")
    industry     = org_context.get("industry", "unspecified industry")
    size         = org_context.get("size", "unspecified size")
    maturity     = org_context.get("maturity_level", "unspecified maturity level")
    domain_name  = org_context.get("domain_name", "data governance")
    target_level = org_context.get("target_level")
    gap          = org_context.get("gap")   # gap = target - current: positive = below target
    from_level   = org_context.get("from_level")
    to_level     = org_context.get("to_level")

    # ── Incremental path (only relevant when below target) ───────────────────
    maturity_path = _build_maturity_path(from_level, to_level, target_level)

    # ── Gap-aware context string ─────────────────────────────────────────────
    if gap is not None and target_level is not None:
        if gap > 0:
            # Below target — needs improvement
            gap_context = (
                f"on the KPI \"{kpi_name}\", {org_name} is currently at maturity level L{maturity}, "
                f"which is {gap} level(s) below their target of L{target_level}. "
                f"This is a gap that needs to be addressed."
            )
            standing_instruction = (
                f"Explain what being at L{maturity} means in practice for a {size} {industry} organization "
                f"on this KPI, and the implications of being {gap} level(s) below their target of L{target_level}."
            )

            if maturity_path:
                # Multi-step gap: explain this is the first step of a longer journey
                path_note = (
                    f" The full improvement path to reach L{target_level} is: {maturity_path}. "
                    f"This action addresses the immediate L{from_level}→L{to_level} step — "
                    f"explain why completing this foundational step is essential before progressing "
                    f"to the subsequent stages."
                )
            else:
                # This action directly reaches the target
                path_note = (
                    f" This action is the final step to reach the target of L{target_level}."
                )

            action_instruction = (
                f"Explain how the recommended action helps {org_name} close this gap, "
                f"tailored to their industry and size. Be concrete and practical.{path_note}"
            )

        elif gap == 0:
            # On target — sustain
            gap_context = (
                f"on the KPI \"{kpi_name}\", {org_name} is currently at maturity level L{maturity}, "
                f"which meets their target of L{target_level}. "
                f"The focus should be on sustaining and reinforcing current practices."
            )
            standing_instruction = (
                f"Acknowledge that {org_name} has reached their target on this KPI "
                f"and describe what operating at L{maturity} looks like in practice "
                f"for a {size} {industry} organization."
            )
            action_instruction = (
                f"Explain how the recommended action helps {org_name} sustain and embed "
                f"this level of maturity to prevent regression and continue driving value."
            )

        else:
            # Above target — leverage strength (gap < 0)
            gap_context = (
                f"on the KPI \"{kpi_name}\", {org_name} is currently at maturity level L{maturity}, "
                f"which exceeds their target of L{target_level} by {abs(gap)} level(s). "
                f"This is an area of strength."
            )
            standing_instruction = (
                f"Acknowledge that {org_name} is performing above target on this KPI "
                f"and describe what this advanced maturity (L{maturity}) looks like in practice "
                f"for a {size} {industry} organization."
            )
            action_instruction = (
                f"Explain how the recommended action allows {org_name} to leverage and extend "
                f"this strength — sharing best practices internally and using it as a foundation "
                f"for broader governance maturity."
            )
    else:
        gap_context = (
            f"on the KPI \"{kpi_name}\", {org_name} is currently at maturity level L{maturity}."
        )
        standing_instruction = (
            f"Describe what being at L{maturity} means in practice for a {size} {industry} organization "
            f"on this specific KPI."
        )
        action_instruction = (
            f"Explain how the recommended action applies specifically to {org_name} "
            f"given their industry and size. Be concrete and practical."
        )

    # ── Similar orgs section ─────────────────────────────────────────────────
    similar_orgs_text = ""
    if similar_orgs:
        entries = []
        for o in similar_orgs:
            notes = f" {o['notes']}" if o['notes'] else ""
            entries.append(
                f"- A {o['size']} {o['industry']} organization at L{o['maturity']} "
                f"rated this action {o['rating']}/5.{notes}"
            )
        similar_orgs_text = "\n".join(entries)

    similarity_instruction = ""
    if similar_orgs_text:
        similarity_instruction = f"""
The following similar organizations have implemented this action:

{similar_orgs_text}

End paragraph 2 with exactly 1-2 sentences summarizing what similar organizations achieved \
with this action — do not name them directly."""

    # ── System prompt ────────────────────────────────────────────────────────
    system_prompt = (
        "You are a senior data governance consultant at KPMG. "
        "Write concise, professional consulting narratives tailored to a specific organization. "
        "Be direct and practical. Do not use bullet points. Avoid filler phrases and repetition. "
        "Never recommend improvement actions for organizations already at or above their target — "
        "focus on sustaining or leveraging existing strengths instead. "
        "Never contradict yourself — if the organization is above target, do not describe deficiencies. "
        "When describing an incremental improvement path, make clear that each step builds on the "
        "previous one and that the current action is the mandatory foundation."
    )

    # ── User prompt ──────────────────────────────────────────────────────────
    user_prompt = f"""You are writing a recommendation narrative for {org_name}, \
a {size} organization in the {industry} industry.

Context: {gap_context}

The recommended action is:
\"{action_text}\"

Use the following reference material to enrich your narrative:
{chunks_text}
{similarity_instruction}

Write exactly 2 paragraphs (max 90 words each):

Paragraph 1 — Current standing:
{standing_instruction}

Paragraph 2 — Action in context:
{action_instruction}
{"End with 1-2 sentences on what similar organizations achieved with this action." if similar_orgs_text else ""}

Do not use bullet points. Do not start both paragraphs the same way. Write in flowing prose."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt}
    ]

    logger.debug(
        "Prompt built for KPI: %s | org: %s | %s %s L%s → L%s (action: L%s→L%s) | gap: %s | path: %s | similar_orgs: %d",
        kpi_name, org_name, industry, size, maturity,
        target_level, from_level, to_level, gap,
        maturity_path or "none", len(similar_orgs or [])
    )
    return messages
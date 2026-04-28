import logging

logger = logging.getLogger(__name__)


def build_prompt(
    kpi_name: str,
    action_text: str,
    org_context: dict,
    retrieved_chunks: list[dict],
    similar_orgs: list[dict] = None
) -> list[dict]:
    """
    Builds the messages array for the OpenAI chat completion API.

    Args:
        kpi_name:         Name of the KPI being recommended on
        action_text:      The Layer 1 base action text
        org_context:      Dict with keys: org_name, industry, size, maturity_level, domain_name
        retrieved_chunks: List of dicts from retriever.retrieve_chunks()
        similar_orgs:     List of dicts with keys: industry, size, maturity, rating, notes

    Returns:
        A messages list ready to pass to openai.chat.completions.create()
    """

    # Format retrieved chunks
    if retrieved_chunks:
        chunks_text = "\n\n".join([
            f"Reference {i+1}:\n{chunk['chunk_text']}"
            for i, chunk in enumerate(retrieved_chunks)
        ])
    else:
        chunks_text = "No additional reference material available."

    org_name    = org_context.get("org_name", "the organization")
    industry    = org_context.get("industry", "unspecified industry")
    size        = org_context.get("size", "unspecified size")
    maturity    = org_context.get("maturity_level", "unspecified maturity level")
    domain_name = org_context.get("domain_name", "data governance")

    # Format similar org implementations if available
    similar_orgs_text = ""
    if similar_orgs:
        entries = []
        for o in similar_orgs:
            rating_stars = o['rating']
            notes = f" Notes: {o['notes']}" if o['notes'] else ""
            entries.append(
                f"- A {o['size']} organization in {o['industry']} "
                f"(maturity L{o['maturity']}) rated this action {rating_stars}/5.{notes}"
            )
        similar_orgs_text = "\n".join(entries)

    # Build similarity paragraph instruction only if data exists
    similarity_instruction = ""
    similarity_section = ""
    if similar_orgs_text:
        similarity_section = f"""
The following organizations have implemented a similar action and rated it highly:

{similar_orgs_text}
"""
        similarity_instruction = "3. In a third short paragraph, briefly reference that similar organizations have successfully implemented this type of action and what it led to — use the data above but do not name organizations directly."

    system_prompt = (
        "You are a senior data governance consultant at KPMG. "
        "Your role is to write concise, actionable consulting recommendations "
        "tailored to a specific organization's context. "
        "Write in a professional consulting tone — clear, direct, and practical. "
        "Do not use bullet points. Be direct and concise — avoid repetition and filler phrases."
    )

    paragraph_count = "3 short paragraphs" if similar_orgs_text else "2 short paragraphs"

    user_prompt = f"""You are advising {org_name}, a {size} organization in the {industry} industry.
Their current maturity level on the {domain_name} dimension is {maturity}.

The recommended action for {org_name} is:
\"{action_text}\"

Use the following reference material to enrich and contextualize your recommendation:

{chunks_text}
{similarity_section}
Write a concise {paragraph_count} (max 100 words per paragraph) that:
1. Explains why this action is relevant and urgent for {org_name} given their industry and maturity level
2. Describes concretely how they should implement it
{similarity_instruction}

Do not use bullet points. Do not repeat the action verbatim. Write in flowing paragraphs."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt}
    ]

    logger.debug(
        "Prompt built for KPI: %s | org: %s | %s %s L%s | similar_orgs: %d",
        kpi_name, org_name, industry, size, maturity, len(similar_orgs or [])
    )
    return messages
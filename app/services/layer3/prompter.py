import logging

logger = logging.getLogger(__name__)


def build_prompt(
    kpi_name: str,
    action_text: str,
    org_context: dict,
    retrieved_chunks: list[dict]
) -> list[dict]:
    """
    Builds the messages array for the OpenAI chat completion API.

    Args:
        kpi_name:         Name of the KPI being recommended on
        action_text:      The Layer 1 base action text
        org_context:      Dict with keys: org_name, industry, size, maturity_level, domain_name
        retrieved_chunks: List of dicts from retriever.retrieve_chunks()

    Returns:
        A messages list ready to pass to openai.chat.completions.create()
    """

    # Format retrieved chunks into readable reference material
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

    system_prompt = (
        "You are a senior data governance consultant at KPMG. "
        "Your role is to write concise, actionable consulting recommendations "
        "tailored to a specific organization's context. "
        "Write in a professional consulting tone — clear, direct, and practical. "
        "Do not use bullet points. Write 2 to 3 cohesive paragraphs."
    )

    user_prompt = f"""You are advising {org_name}, a {size} organization in the {industry} industry.
Their current maturity level on the {domain_name} dimension is {maturity}.

The recommended action for {org_name} is:
\"{action_text}\"

Use the following reference material to enrich and contextualize your recommendation:

{chunks_text}

Write a 2 to 3 paragraph consulting narrative that:
1. Explains why this action is relevant and urgent for {org_name} given their industry and maturity level
2. Describes concretely how they should implement it
3. States the expected business impact if they succeed

Do not repeat the action verbatim. Do not use bullet points. Write in flowing paragraphs."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt}
    ]

    logger.debug("Prompt built for KPI: %s | org: %s | %s %s L%s", kpi_name, org_name, industry, size, maturity)
    return messages
"""
app/services/layer2/normalizer.py
----------------------------------
Two Groq-powered functions:

1. normalize_industry(raw_text)
   Normalizes free-text industry names into clean canonical names.
   Used when organization.industry = 'Other' and industry_other is filled.

2. generate_company_description(name, industry, size_band, country)
   Auto-generates a rich company description from basic org fields.
   Called when a new organization is created via POST /api/organizations.
   Stored in organizations.company_description for Layer 2 embedding.
"""

import logging
import os

import requests

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL   = "llama-3.1-8b-instant"


def _call_groq(prompt: str, max_tokens: int = 100) -> str | None:
    """
    Shared Groq API call helper.
    Returns the response text or None on failure.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.warning("[Normalizer] GROQ_API_KEY not set")
        return None

    try:
        response = requests.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROQ_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": 0,
            },
            timeout=10,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()

    except Exception as e:
        logger.warning(f"[Normalizer] Groq call failed: {e}")
        return None


# ── 1. Industry normalization ────────────────────────────────

def normalize_industry(raw_text: str) -> str:
    """
    Normalize a free-text industry name into a clean canonical name.

    Args:
        raw_text: raw industry text typed by user e.g. "law firm"

    Returns:
        clean canonical industry name e.g. "Legal Services"
    """
    if not raw_text or not raw_text.strip():
        return "Other"

    prompt = (
        f'You are an industry name normalizer.\n'
        f'The user described their industry as: "{raw_text}"\n'
        f'Return ONLY a clean, standardized English industry name in Title Case.\n'
        f'2-3 words maximum. No explanation. No punctuation.\n'
        f'Examples:\n'
        f'"law firm" -> "Legal Services"\n'
        f'"banque" -> "Banking"\n'
        f'"sante" -> "Healthcare"\n'
        f'"make cars" -> "Automotive"\n'
        f'"sell food online" -> "E-Commerce"\n'
    )

    result = _call_groq(prompt, max_tokens=20)
    if result:
        logger.info(f"[Normalizer] Industry normalized: '{raw_text}' -> '{result}'")
        return result

    logger.warning("[Normalizer] Falling back to Title Case")
    return raw_text.strip().title()


def resolve_industry_label(industry: str, industry_other: str | None) -> str:
    """
    Return the effective industry label for an organization.
    If industry = 'Other', normalize industry_other via Groq.
    Otherwise return industry as-is.

    Args:
        industry:       fixed enum value e.g. "Banking" or "Other"
        industry_other: free text typed by user, only set when industry = "Other"

    Returns:
        clean industry label ready for embedding
    """
    if industry == "Other" and industry_other:
        return normalize_industry(industry_other)
    return industry


# ── 2. Company description generation ───────────────────────

def generate_company_description(
    name: str,
    industry: str,
    industry_other: str | None,
    size_band: str,
    country: str,
) -> str:
    """
    Auto-generate a rich company description from basic org fields.
    Called when a new organization is created.
    Stored in organizations.company_description for Layer 2 embedding.

    Args:
        name:           company name e.g. "STAR Insurance"
        industry:       fixed enum e.g. "Insurance" or "Other"
        industry_other: free text if industry = "Other" e.g. "Legal Services"
        size_band:      "SME" / "Large" / "Enterprise"
        country:        e.g. "Tunisia"

    Returns:
        rich description string e.g.
        "SME insurance company offering life insurance, property coverage,
         auto insurance, risk assessment, claims management and financial
         protection products to individual and corporate clients in Tunisia"
    """
    # resolve effective industry label
    effective_industry = resolve_industry_label(industry, industry_other)

    prompt = (
        f'Generate a concise professional description for a company with these details:\n'
        f'  Name:     {name}\n'
        f'  Industry: {effective_industry}\n'
        f'  Size:     {size_band}\n'
        f'  Country:  {country}\n\n'
        f'Requirements:\n'
        f'- 1-2 sentences maximum\n'
        f'- Include the main business activities and services\n'
        f'- Include relevant industry keywords for data similarity matching\n'
        f'- Do not mention the company name in the description\n'
        f'- No introduction, no explanation, just the description\n\n'
        f'Examples:\n'
        f'Insurance SME Tunisia -> "SME insurance company offering life insurance, '
        f'property coverage, auto insurance, risk assessment, claims management '
        f'and financial protection products to individual and corporate clients in Tunisia"\n'
        f'Banking Large Tunisia -> "Large retail and corporate bank providing mortgage loans, '
        f'deposit accounts, trade finance, digital banking and wealth management '
        f'services to individuals and businesses in Tunisia"\n'
    )

    result = _call_groq(prompt, max_tokens=120)
    if result:
        logger.info(f"[Normalizer] Description generated for {name}: {result[:60]}...")
        return result

    # fallback: basic description
    logger.warning(f"[Normalizer] Description generation failed for {name} — using fallback")
    return f"{size_band} {effective_industry.lower()} company operating in {country}"
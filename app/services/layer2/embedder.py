"""
app/services/layer2/embedder.py
--------------------------------
Embeds organizations using two signals combined:
  - Industry label (30%) → broad sector similarity
  - Company description (70%) → specific activity similarity

Model: all-MiniLM-L6-v2 (lazy loaded once, reused across calls)
"""

import logging
from typing import Optional

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)

_model: Optional[SentenceTransformer] = None
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

INDUSTRY_EMBED_WEIGHT    = 0.30
DESCRIPTION_EMBED_WEIGHT = 0.70


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info(f"[Embedder] Loading model {MODEL_NAME}...")
        _model = SentenceTransformer(MODEL_NAME)
        logger.info("[Embedder] Model loaded successfully")
    return _model


def embed_organization(industry_label: str, company_description: str) -> np.ndarray:
    """
    Embed a single organization by combining industry and description embeddings.

    Args:
        industry_label:      resolved industry name e.g. "Banking" or "Legal Services"
        company_description: free text describing the org's activities

    Returns:
        combined embedding of shape (384,) — normalized
    """
    model = _get_model()

    industry_emb     = model.encode([industry_label],       normalize_embeddings=True)[0]
    description_emb  = model.encode([company_description],  normalize_embeddings=True)[0]

    combined = (
        INDUSTRY_EMBED_WEIGHT    * industry_emb +
        DESCRIPTION_EMBED_WEIGHT * description_emb
    )

    norm = np.linalg.norm(combined)
    if norm > 0:
        combined = combined / norm

    return combined


def embed_organizations(orgs: list[dict]) -> np.ndarray:
    """
    Embed a list of organizations.

    Args:
        orgs: list of dicts with keys 'industry_label' and 'company_description'

    Returns:
        numpy array of shape (N, 384)
    """
    if not orgs:
        return np.array([])

    embeddings = np.array([
        embed_organization(o["industry_label"], o["company_description"])
        for o in orgs
    ])

    logger.info(f"[Embedder] Embedded {len(orgs)} organizations")
    return embeddings


def compute_org_similarity(current_embedding: np.ndarray, past_embeddings: np.ndarray) -> np.ndarray:
    """
    Compute cosine similarity between current org and all past orgs.

    Args:
        current_embedding: shape (384,)
        past_embeddings:   shape (N, 384)

    Returns:
        numpy array of shape (N,) — similarity scores 0 to 1
    """
    current = current_embedding.reshape(1, -1)
    sims    = cosine_similarity(current, past_embeddings)[0]
    return sims
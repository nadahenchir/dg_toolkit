"""
KNN similarity matching for Layer 2.

Builds feature vectors per assessment and finds the K most
similar past assessments using combined similarity:
  - 50% organization embedding (industry + description)
  - 50% maturity feature vector (size + overall + 11 domain levels)

Returns top-K matches with their similarity scores.
"""

import logging
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from app.db.connection import get_connection
from app.services.layer2.normalizer import resolve_industry_label
from app.services.layer2.embedder import embed_organization, compute_org_similarity

logger = logging.getLogger(__name__)

# weights for combining org embedding and maturity similarity
ORG_EMBED_WEIGHT = 0.50
MATURITY_WEIGHT  = 0.50

# KNN K value
K = 3

# size band encoding order
SIZE_BANDS = ["SME", "Large", "Enterprise"]


# ── feature vector ───────────────────────────────────────────

def build_maturity_vector(size_band: str, overall_level: int, domain_levels: list) -> np.ndarray:
    """
    Build a 15-element numeric feature vector:
      - 3 one-hot for size_band
      - 1 overall maturity level (1–5)
      - 11 domain maturity levels (1–5)

    Args:
        size_band:     "SME" / "Large" / "Enterprise"
        overall_level: 1–5
        domain_levels: list of 11 integers 1–5

    Returns:
        numpy array of shape (15,)
    """
    size_onehot = [1 if size_band == s else 0 for s in SIZE_BANDS]
    vector = np.array(size_onehot + [overall_level] + domain_levels, dtype=float)

    # normalize
    norm = np.linalg.norm(vector)
    if norm > 0:
        vector = vector / norm

    return vector


# ── DB helpers ───────────────────────────────────────────────

def fetch_assessment_profile(conn, assessment_id: int) -> dict | None:
    """
    Fetch all data needed to build feature vector and embedding
    for a given assessment.

    Returns dict with keys:
        industry, industry_other, size_band, company_description,
        overall_level, domain_levels (list of 11 ints)
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT o.industry, o.industry_other, o.size_band,
                   o.company_description, s.overall_level
            FROM dg_toolkit.assessments a
            JOIN dg_toolkit.organizations o     ON o.id = a.organization_id
            JOIN dg_toolkit.assessment_scores s ON s.assessment_id = a.id
            WHERE a.id = %s AND a.deleted_at IS NULL
        """, (assessment_id,))
        row = cur.fetchone()
        if not row:
            return None

        industry, industry_other, size_band, company_description, overall_level = row

        # fetch 11 domain levels ordered by domain_id
        cur.execute("""
            SELECT domain_id, COALESCE(maturity_level, 1)
            FROM dg_toolkit.domain_scores
            WHERE assessment_id = %s
            ORDER BY domain_id
        """, (assessment_id,))
        domain_rows   = cur.fetchall()
        domain_levels = [r[1] for r in domain_rows]

        # pad to 11 if any domain missing
        while len(domain_levels) < 11:
            domain_levels.append(1)

    return {
        "industry":            industry,
        "industry_other":      industry_other,
        "size_band":           size_band or "SME",
        "company_description": company_description or "",
        "overall_level":       overall_level,
        "domain_levels":       domain_levels[:11],
    }


def fetch_eligible_past_assessments(conn, current_id: int) -> list[int]:
    """
    Fetch IDs of past assessments eligible for KNN matching:
      - not the current assessment
      - not soft-deleted
      - layer2_status = done (fully processed)
      - has at least one rated recommendation (was_implemented + rating)
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT a.id
            FROM dg_toolkit.assessments a
            JOIN dg_toolkit.recommendations r ON r.assessment_id = a.id
            WHERE a.id != %s
              AND a.deleted_at IS NULL
              AND a.layer2_status = 'done'
              AND r.was_implemented = true
              AND r.implementation_rating >= 4
        """, (current_id,))
        return [row[0] for row in cur.fetchall()]


# ── combined similarity ───────────────────────────────────────

def compute_combined_similarity(
    current_profile:  dict,
    past_profiles:    dict[int, dict],
) -> dict[int, float]:
    """
    Compute combined similarity between current assessment and
    all past assessments.

    Combined score = 50% org embedding + 50% maturity vector

    Args:
        current_profile: profile dict for current assessment
        past_profiles:   {assessment_id: profile dict} for past assessments

    Returns:
        {assessment_id: combined_similarity_score}
    """
    if not past_profiles:
        return {}

    past_ids = list(past_profiles.keys())

    # ── org embeddings ────────────────────────────────────────
    current_label = resolve_industry_label(
        current_profile["industry"],
        current_profile["industry_other"]
    )
    current_org_emb = embed_organization(
        current_label,
        current_profile["company_description"]
    )

    past_org_embs = np.array([
        embed_organization(
            resolve_industry_label(past_profiles[pid]["industry"], past_profiles[pid]["industry_other"]),
            past_profiles[pid]["company_description"]
        )
        for pid in past_ids
    ])

    org_sims = compute_org_similarity(current_org_emb, past_org_embs)

    # ── maturity feature vectors ──────────────────────────────
    current_vec = build_maturity_vector(
        current_profile["size_band"],
        current_profile["overall_level"],
        current_profile["domain_levels"],
    )

    past_vecs = np.array([
        build_maturity_vector(
            past_profiles[pid]["size_band"],
            past_profiles[pid]["overall_level"],
            past_profiles[pid]["domain_levels"],
        )
        for pid in past_ids
    ])

    maturity_sims = cosine_similarity(
        current_vec.reshape(1, -1),
        past_vecs
    )[0]

    # ── combine ───────────────────────────────────────────────
    combined = ORG_EMBED_WEIGHT * org_sims + MATURITY_WEIGHT * maturity_sims

    return {past_ids[i]: float(combined[i]) for i in range(len(past_ids))}


# ── KNN ───────────────────────────────────────────────────────

def find_top_k_similar(
    assessment_id: int,
    conn=None,
) -> tuple[list[int], dict[int, float], str]:
    """
    Main KNN function. Finds the K most similar past assessments
    to the given assessment.

    Args:
        assessment_id: current assessment ID
        conn:          optional DB connection (creates one if not provided)

    Returns:
        tuple of:
          - top_k_ids:   list of up to K past assessment IDs
          - similarities: {assessment_id: similarity_score}
          - confidence:  'high' / 'medium' / 'low' / 'none'
    """
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True

    try:
        # fetch current profile
        current_profile = fetch_assessment_profile(conn, assessment_id)
        if not current_profile:
            raise ValueError(f"Assessment {assessment_id} not found or missing scores")

        # fetch eligible past assessments
        past_ids = fetch_eligible_past_assessments(conn, assessment_id)
        logger.info(f"[KNN] Found {len(past_ids)} eligible past assessments")

        if not past_ids:
            return [], {}, "none"

        # fetch profiles for all past assessments
        past_profiles = {}
        for pid in past_ids:
            profile = fetch_assessment_profile(conn, pid)
            if profile:
                past_profiles[pid] = profile

        if not past_profiles:
            return [], {}, "none"

        # compute combined similarity
        similarities = compute_combined_similarity(current_profile, past_profiles)

        # sort by similarity descending, take top K
        sorted_ids = sorted(similarities.keys(), key=lambda x: similarities[x], reverse=True)
        top_k_ids  = sorted_ids[:K]
        top_k_sims = {pid: similarities[pid] for pid in top_k_ids}

        avg_sim    = float(np.mean(list(top_k_sims.values())))
        confidence = _compute_confidence(len(top_k_ids), avg_sim)

        logger.info(
            f"[KNN] Top-{len(top_k_ids)} matches: {top_k_ids} "
            f"avg_sim={avg_sim:.3f} confidence={confidence}"
        )

        return top_k_ids, top_k_sims, confidence

    finally:
        if close_conn:
            conn.close()


def _compute_confidence(k_found: int, avg_similarity: float) -> str:
    """Determine confidence level based on match quality."""
    if k_found == 0:
        return "none"
    if k_found >= 3 and avg_similarity >= 0.80:
        return "high"
    if k_found >= 2 and avg_similarity >= 0.60:
        return "medium"
    return "low"
"""
app/services/layer2/booster.py
--------------------------------
Computes priority score boost per KPI using KNN results
and updates the recommendations table.

For each KPI in the current assessment:
  - Check if it appears in highly rated recommendations
    from the top-K similar past assessments
  - Compute boost = avg_similarity × (avg_rating / 5) × BOOST_FACTOR
  - Update priority_score = 1.0 + boost
  - Set layer2_confidence on every recommendation
"""

import logging
import numpy as np

from app.db.connection import get_connection

logger = logging.getLogger(__name__)

BOOST_FACTOR = 0.20   # max boost added to priority_score
MIN_RATING   = 4      # minimum rating to count as signal


def fetch_rated_recommendations(conn, assessment_ids: list[int]) -> list[tuple]:
    """
    Fetch highly rated recommendations from a list of past assessments.

    Returns list of (assessment_id, kpi_id, implementation_rating)
    """
    if not assessment_ids:
        return []

    with conn.cursor() as cur:
        cur.execute("""
            SELECT assessment_id, kpi_id, implementation_rating
            FROM dg_toolkit.recommendations
            WHERE assessment_id = ANY(%s)
              AND was_implemented = true
              AND implementation_rating >= %s
        """, (assessment_ids, MIN_RATING))
        return cur.fetchall()


def compute_boosts(
    similarities: dict[int, float],
    rated_recs:   list[tuple],
) -> dict[int, float]:
    """
    Compute boost per KPI based on KNN matches and their ratings.

    Args:
        similarities: {assessment_id: similarity_score}
        rated_recs:   list of (assessment_id, kpi_id, rating)

    Returns:
        {kpi_id: boost_value}
    """
    # group signals by kpi_id
    kpi_signals: dict[int, list[tuple[float, int]]] = {}

    for (past_assessment_id, kpi_id, rating) in rated_recs:
        if past_assessment_id not in similarities:
            continue
        sim = similarities[past_assessment_id]
        kpi_signals.setdefault(kpi_id, []).append((sim, rating))

    # compute boost per KPI
    boosts = {}
    for kpi_id, signals in kpi_signals.items():
        avg_sim    = float(np.mean([s for s, _ in signals]))
        avg_rating = float(np.mean([r for _, r in signals]))
        boost      = avg_sim * (avg_rating / 5.0) * BOOST_FACTOR
        boosts[kpi_id] = round(boost, 6)

    return boosts


def apply_boosts(
    conn,
    assessment_id: int,
    boosts:        dict[int, float],
    confidence:    str,
) -> None:
    """
    Update recommendations table with computed boosts and confidence.

    Args:
        conn:          DB connection
        assessment_id: current assessment ID
        boosts:        {kpi_id: boost_value}
        confidence:    'high' / 'medium' / 'low' / 'none'
    """
    with conn.cursor() as cur:
        # fetch all KPI IDs for this assessment
        cur.execute("""
            SELECT kpi_id
            FROM dg_toolkit.recommendations
            WHERE assessment_id = %s
        """, (assessment_id,))
        all_kpi_ids = [row[0] for row in cur.fetchall()]

    boosted  = 0
    unboosted = 0

    with conn.cursor() as cur:
        for kpi_id in all_kpi_ids:
            boost = boosts.get(kpi_id, 0.0)

            cur.execute("""
                UPDATE dg_toolkit.recommendations
                SET priority_score    = 1.0 + %s,
                    layer2_confidence = %s
                WHERE assessment_id = %s
                  AND kpi_id = %s
            """, (boost, confidence, assessment_id, kpi_id))

            if boost > 0:
                boosted += 1
            else:
                unboosted += 1

    logger.info(
        f"[Booster] Assessment {assessment_id}: "
        f"{boosted} KPIs boosted, {unboosted} unchanged "
        f"confidence={confidence}"
    )


def run_booster(
    assessment_id: int,
    top_k_ids:     list[int],
    similarities:  dict[int, float],
    confidence:    str,
    conn=None,
) -> None:
    """
    Main booster entry point. Called by runner.py after KNN.

    Args:
        assessment_id: current assessment ID
        top_k_ids:     list of top-K past assessment IDs from KNN
        similarities:  {assessment_id: similarity_score} from KNN
        confidence:    confidence level from KNN
        conn:          optional DB connection
    """
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True

    try:
        if not top_k_ids:
            # no matches — set all to default with confidence=none
            logger.info(f"[Booster] No KNN matches for assessment {assessment_id} — skipping boost")
            apply_boosts(conn, assessment_id, {}, "none")
            conn.commit()
            return

        # fetch rated recommendations from top-K matches
        rated_recs = fetch_rated_recommendations(conn, top_k_ids)
        logger.info(
            f"[Booster] Found {len(rated_recs)} rated recommendations "
            f"from {len(top_k_ids)} similar assessments"
        )

        # compute boosts
        boosts = compute_boosts(similarities, rated_recs)
        logger.info(f"[Booster] Computed boosts for {len(boosts)} KPIs")

        # apply to DB
        apply_boosts(conn, assessment_id, boosts, confidence)
        conn.commit()

    finally:
        if close_conn:
            conn.close()
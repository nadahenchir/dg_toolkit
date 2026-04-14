"""
app/services/layer2/runner.py
------------------------------
Orchestrates the full Layer 2 pipeline:
  1. Mark layer2_status = 'running'
  2. Run KNN to find top-K similar past assessments
  3. Run booster to compute and apply priority score boosts
  4. Mark layer2_status = 'done'
  5. Trigger Layer 3

Called automatically after Layer 1 completes.
Can also be triggered manually via POST /api/assessments/{id}/layer2/run
"""

import logging

from app.db.connection import get_connection
from app.services.layer2.knn import find_top_k_similar
from app.services.layer2.booster import run_booster

logger = logging.getLogger(__name__)


def run_layer2(assessment_id: int) -> None:
    """
    Main Layer 2 entry point.

    Args:
        assessment_id: assessment to process
    """
    logger.info(f"[Layer2] Starting for assessment {assessment_id}")
    conn = get_connection()

    try:
        # ── 1. mark as running ────────────────────────────────
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE dg_toolkit.assessments
                SET layer2_status = 'running'
                WHERE id = %s
            """, (assessment_id,))
        conn.commit()

        # ── 2. KNN — find top-K similar past assessments ──────
        logger.info(f"[Layer2] Running KNN for assessment {assessment_id}")
        top_k_ids, similarities, confidence = find_top_k_similar(
            assessment_id, conn=conn
        )
        logger.info(
            f"[Layer2] KNN complete — "
            f"top_k={top_k_ids} confidence={confidence}"
        )

        # ── 3. booster — compute and apply priority scores ────
        logger.info(f"[Layer2] Running booster for assessment {assessment_id}")
        run_booster(
            assessment_id = assessment_id,
            top_k_ids     = top_k_ids,
            similarities  = similarities,
            confidence    = confidence,
            conn          = conn,
        )

        # ── 4. mark as done ───────────────────────────────────
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE dg_toolkit.assessments
                SET layer2_status = 'done'
                WHERE id = %s
            """, (assessment_id,))
        conn.commit()

        logger.info(f"[Layer2] Completed for assessment {assessment_id}")

        # ── 5. trigger Layer 3 ────────────────────────────────
        _trigger_layer3(assessment_id)

    except Exception as e:
        logger.error(f"[Layer2] Failed for assessment {assessment_id}: {e}")
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE dg_toolkit.assessments
                    SET layer2_status = 'failed'
                    WHERE id = %s
                """, (assessment_id,))
            conn.commit()
        except Exception:
            pass
        raise

    finally:
        conn.close()


def _trigger_layer3(assessment_id: int) -> None:
    """
    Trigger Layer 3 after Layer 2 completes.
    Uncomment the import and call once layer3 is built.
    """
    logger.info(
        f"[Layer2] → Layer 3 trigger placeholder "
        f"for assessment {assessment_id}"
    )
    # from app.services.layer3 import run_layer3
    # run_layer3(assessment_id)
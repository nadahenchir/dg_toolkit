"""
app/services/layer1.py
----------------------
Layer 1 — Rule-based recommendations from action_library.

Pipeline position:
    submit → scoring → [layer1] → layer2 → layer3 → report ready

Triggered automatically by scoring.py after scoring_status = 'done'.

Logic:
    1. Fetch all non-excluded KPI scores for the assessment.
    2. For each KPI where maturity_level < 5, look up the matching action in
       action_library (kpi_id + from_level = maturity_level).
    3. Derive action_category from impact/effort at insert time.
    4. Upsert one row per KPI into recommendations with priority_score = 1.0.
    5. Trigger Layer 2 automatically on success — outside the try/except
       so Layer 2 failures are not misreported as Layer 1 failures.
    6. On any Layer 1 failure, set layer2_status = 'failed' and re-raise.

action_category derivation:
    High impact + Low effort  → Quick Win
    High impact + High effort → Strategic
    anything else             → Fill In
"""

import logging
from app.db.connection import get_connection

logger = logging.getLogger(__name__)


def _derive_category(impact: str, effort: str) -> str:
    impact = (impact or '').strip().lower()
    effort = (effort or '').strip().lower()
    if impact == 'high' and effort == 'low':
        return 'Quick Win'
    if impact == 'high' and effort == 'high':
        return 'Strategic'
    return 'Fill In'


def run_layer1(assessment_id: int) -> dict:
    """
    Generate Layer 1 recommendations for a scored assessment.

    Returns a summary dict:
        {
            'inserted':  <int>,   # new recommendation rows created
            'updated':   <int>,   # existing rows refreshed (re-run)
            'skipped':   <int>,   # KPIs at level 5 or excluded
        }

    Raises on any DB or logic error — caller must handle.
    """
    conn = get_connection()
    try:
        # -- 1. guard: confirm scoring is done --------------------------------
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT scoring_status
                FROM   dg_toolkit.assessments
                WHERE  id = %s AND deleted_at IS NULL
                """,
                (assessment_id,),
            )
            row = cur.fetchone()

        if not row:
            raise ValueError(f"Assessment {assessment_id} not found.")
        if row[0] != 'done':
            raise ValueError(
                f"Cannot run Layer 1: scoring_status is '{row[0]}', expected 'done'."
            )

        # -- 2. fetch non-excluded KPI scores ---------------------------------
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ks.kpi_id,
                       ks.maturity_level
                FROM   dg_toolkit.kpi_scores ks
                WHERE  ks.assessment_id = %s
                  AND  ks.is_excluded   = false
                  AND  ks.maturity_level IS NOT NULL
                ORDER  BY ks.kpi_id
                """,
                (assessment_id,),
            )
            kpi_rows = cur.fetchall()

        inserted = 0
        updated  = 0
        skipped  = 0

        for kpi_id, maturity_level in kpi_rows:
            # KPI already at max — no action exists for from_level = 5
            if maturity_level >= 5:
                skipped += 1
                continue

            # -- 3. look up action in action_library --------------------------
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, impact, effort
                    FROM   dg_toolkit.action_library
                    WHERE  kpi_id     = %s
                      AND  from_level = %s
                    """,
                    (kpi_id, maturity_level),
                )
                action = cur.fetchone()

            if not action:
                logger.warning(
                    "Layer 1: no action found for kpi_id=%s from_level=%s — skipping.",
                    kpi_id, maturity_level,
                )
                skipped += 1
                continue

            action_id, impact, effort = action
            category = _derive_category(impact, effort)

            # -- 4. upsert recommendation row ---------------------------------
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO dg_toolkit.recommendations
                        (assessment_id, kpi_id, base_action_id, action_category, priority_score)
                    VALUES (%s, %s, %s, %s, 1.0)
                    ON CONFLICT (assessment_id, kpi_id)
                    DO UPDATE SET
                        base_action_id  = EXCLUDED.base_action_id,
                        action_category = EXCLUDED.action_category,
                        priority_score  = 1.0
                    RETURNING (xmax = 0) AS was_inserted
                    """,
                    (assessment_id, kpi_id, action_id, category),
                )
                was_inserted = cur.fetchone()[0]
                if was_inserted:
                    inserted += 1
                else:
                    updated += 1

        # -- 5. commit all recommendation rows --------------------------------
        conn.commit()

        summary = {
            'inserted': inserted,
            'updated':  updated,
            'skipped':  skipped,
        }
        logger.info("Layer 1 complete for assessment %s: %s", assessment_id, summary)

    except Exception:
        # Layer 1 failed — mark and re-raise
        # Layer 2 has not been called yet so layer2_status = 'failed' is correct
        try:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE dg_toolkit.assessments
                    SET    layer2_status = 'failed'
                    WHERE  id = %s
                    """,
                    (assessment_id,),
                )
            conn.commit()
        except Exception:
            pass
        raise

    finally:
        conn.close()

    # -- 6. trigger Layer 2 — outside try/except so Layer 2 failures
    #       are not misreported as Layer 1 failures --------------------
    from app.services.layer2 import run_layer2
    run_layer2(assessment_id)

    return summary
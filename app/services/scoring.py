"""
app/services/scoring.py
-----------------------
Full scoring pipeline:
    kpi_scores → domain_scores → assessment_scores

Triggered automatically from answers.py on submit.
On success, chains into layer1.run_layer1().
"""

import logging
from datetime import datetime, timezone
from app.db.connection import get_connection

logger = logging.getLogger(__name__)


# ------------------------------------------------------------
# Maturity level thresholds
# ------------------------------------------------------------

def resolve_maturity_level(raw_score: float) -> int:
    if raw_score == 0.0:
        return 1
    elif raw_score < 0.50:
        return 2
    elif raw_score < 0.75:
        return 3
    elif raw_score < 1.0:
        return 4
    else:
        return 5


# ------------------------------------------------------------
# Step 1 — KPI scores
# ------------------------------------------------------------

def compute_kpi_scores(assessment_id: int, conn) -> dict:
    """
    For each KPI:
      - Q1 is_na = True  → excluded (raw_score = NULL, is_excluded = True)
      - Q1 raw_value = 0 → L1 immediately, skip Q2-Q4
      - Otherwise        → weighted average of non-hidden, non-NA answers,
                           weights renormalized when questions are missing
    Returns dict: kpi_id → {raw_score, maturity_level, is_excluded}
    """
    with conn.cursor() as cur:
        cur.execute("SELECT id, is_inverted FROM dg_toolkit.kpis")
        kpis = {row[0]: {'is_inverted': row[1]} for row in cur.fetchall()}

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT a.question_id,
                   a.is_na,
                   a.is_hidden,
                   a.raw_value,
                   q.kpi_id,
                   q.question_number,
                   q.weight,
                   q.is_gatekeeper
            FROM   dg_toolkit.answers   a
            JOIN   dg_toolkit.questions q ON q.id = a.question_id
            WHERE  a.assessment_id = %s
            ORDER  BY q.kpi_id, q.question_number
            """,
            (assessment_id,),
        )
        rows = cur.fetchall()

    # Cast Decimal → float immediately
    answers = []
    for r in rows:
        answers.append({
            'question_id':     r[0],
            'is_na':           r[1],
            'is_hidden':       r[2],
            'raw_value':       float(r[3]) if r[3] is not None else None,
            'kpi_id':          r[4],
            'question_number': r[5],
            'weight':          float(r[6]),
            'is_gatekeeper':   r[7],
        })

    # Group by KPI
    kpi_answers: dict = {}
    for a in answers:
        kpi_answers.setdefault(a['kpi_id'], []).append(a)

    kpi_scores: dict = {}
    now = datetime.now(timezone.utc)

    for kpi_id, kpi_ans in kpi_answers.items():
        q1 = next((a for a in kpi_ans if a['question_number'] == 1), None)

        # Q1 = N/A → exclude entire KPI
        if q1 and q1['is_na']:
            kpi_scores[kpi_id] = {
                'raw_score': None, 'maturity_level': None, 'is_excluded': True,
            }
            continue

        # Q1 = Not (0.0) → L1, gate already hid Q2-Q4
        if q1 and q1['raw_value'] == 0.0:
            kpi_scores[kpi_id] = {
                'raw_score': 0.0, 'maturity_level': 1, 'is_excluded': False,
            }
            continue

        # Normal path — scorable = non-hidden, non-NA, has a value
        scorable = [
            a for a in kpi_ans
            if not a['is_hidden'] and not a['is_na'] and a['raw_value'] is not None
        ]

        if not scorable:
            kpi_scores[kpi_id] = {
                'raw_score': 0.0, 'maturity_level': 1, 'is_excluded': False,
            }
            continue

        total_weight = sum(a['weight'] for a in scorable)
        raw_score    = sum(
            (a['weight'] / total_weight) * a['raw_value'] for a in scorable
        )

        if kpis[kpi_id]['is_inverted']:
            raw_score = 1.0 - raw_score

        raw_score = round(raw_score, 4)
        kpi_scores[kpi_id] = {
            'raw_score':      raw_score,
            'maturity_level': resolve_maturity_level(raw_score),
            'is_excluded':    False,
        }

    # Upsert — delete first for idempotency
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM dg_toolkit.kpi_scores WHERE assessment_id = %s",
            (assessment_id,),
        )
        for kpi_id, score in kpi_scores.items():
            cur.execute(
                """
                INSERT INTO dg_toolkit.kpi_scores
                    (assessment_id, kpi_id, raw_score, maturity_level, is_excluded, computed_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    assessment_id,
                    kpi_id,
                    score['raw_score'],
                    score['maturity_level'],
                    score['is_excluded'],
                    now,
                ),
            )

    return kpi_scores


# ------------------------------------------------------------
# Step 2 — Domain scores
# ------------------------------------------------------------

def compute_domain_scores(assessment_id: int, kpi_scores: dict, conn) -> dict:
    """
    Weighted average of non-excluded KPI scores per domain.
    Copies target_level from domain_targets and computes gap.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, domain_id, weight FROM dg_toolkit.kpis ORDER BY domain_id"
        )
        kpis = cur.fetchall()  # (id, domain_id, weight)

    with conn.cursor() as cur:
        cur.execute(
            "SELECT domain_id, target_level FROM dg_toolkit.domain_targets WHERE assessment_id = %s",
            (assessment_id,),
        )
        targets = {r[0]: r[1] for r in cur.fetchall()}

    with conn.cursor() as cur:
        cur.execute("SELECT id, weight FROM dg_toolkit.domains")
        domain_weights = {r[0]: float(r[1]) for r in cur.fetchall()}

    # Group KPIs by domain
    domain_kpis: dict = {}
    for kpi_id, domain_id, weight in kpis:
        domain_kpis.setdefault(domain_id, []).append(
            {'id': kpi_id, 'weight': float(weight)}
        )

    domain_scores: dict = {}
    now = datetime.now(timezone.utc)

    for domain_id, d_kpis in domain_kpis.items():
        scorable = [
            k for k in d_kpis
            if k['id'] in kpi_scores
            and not kpi_scores[k['id']]['is_excluded']
            and kpi_scores[k['id']]['raw_score'] is not None
        ]

        if not scorable:
            continue

        total_weight = sum(k['weight'] for k in scorable)
        raw_score    = round(
            sum(
                (k['weight'] / total_weight) * kpi_scores[k['id']]['raw_score']
                for k in scorable
            ),
            4,
        )
        maturity_level = resolve_maturity_level(raw_score)
        target_level   = targets.get(domain_id)
        gap            = (target_level - maturity_level) if target_level is not None else None

        domain_scores[domain_id] = {
            'raw_score':      raw_score,
            'maturity_level': maturity_level,
            'target_level':   target_level,
            'gap':            gap,
            'kpis_scored':    len(scorable),
        }

    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM dg_toolkit.domain_scores WHERE assessment_id = %s",
            (assessment_id,),
        )
        for domain_id, score in domain_scores.items():
            cur.execute(
                """
                INSERT INTO dg_toolkit.domain_scores
                    (assessment_id, domain_id, raw_score, maturity_level,
                     target_level, gap, kpis_scored, computed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    assessment_id,
                    domain_id,
                    score['raw_score'],
                    score['maturity_level'],
                    score['target_level'],
                    score['gap'],
                    score['kpis_scored'],
                    now,
                ),
            )

    return domain_scores


# ------------------------------------------------------------
# Step 3 — Overall assessment score
# ------------------------------------------------------------

def compute_assessment_score(assessment_id: int, domain_scores: dict, conn) -> dict:
    """
    Weighted average of all domain scores.
    Returns dict with overall_score, overall_level, domains_scored.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT id, weight FROM dg_toolkit.domains")
        domain_weights = {r[0]: float(r[1]) for r in cur.fetchall()}

    scorable = {
        did: s for did, s in domain_scores.items()
        if s['raw_score'] is not None
    }

    if not scorable:
        return None

    total_weight  = sum(domain_weights[did] for did in scorable)
    overall_score = round(
        sum(
            (domain_weights[did] / total_weight) * scorable[did]['raw_score']
            for did in scorable
        ),
        4,
    )
    overall_level  = resolve_maturity_level(overall_score)
    domains_scored = len(scorable)
    now            = datetime.now(timezone.utc)

    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM dg_toolkit.assessment_scores WHERE assessment_id = %s",
            (assessment_id,),
        )
        cur.execute(
            """
            INSERT INTO dg_toolkit.assessment_scores
                (assessment_id, overall_score, overall_level, domains_scored, computed_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (assessment_id, overall_score, overall_level, domains_scored, now),
        )

    return {
        'overall_score':  overall_score,
        'overall_level':  overall_level,
        'domains_scored': domains_scored,
    }


# ------------------------------------------------------------
# Main entry point
# ------------------------------------------------------------

def run_scoring(assessment_id: int):
    """
    Full scoring pipeline: kpi_scores → domain_scores → assessment_scores.
    Sets scoring_status throughout.
    On success, chains into Layer 1.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE dg_toolkit.assessments SET scoring_status = 'running' WHERE id = %s",
                (assessment_id,),
            )
        conn.commit()

        kpi_scores    = compute_kpi_scores(assessment_id, conn)
        domain_scores = compute_domain_scores(assessment_id, kpi_scores, conn)
        overall       = compute_assessment_score(assessment_id, domain_scores, conn)

        if overall is None:
            raise ValueError("No scorable domains found — overall score could not be computed.")

        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE dg_toolkit.assessments
                SET    scoring_status = 'done',
                       scored_at      = NOW(),
                       status         = 'complete'
                WHERE  id = %s
                """,
                (assessment_id,),
            )
        conn.commit()
        logger.info("Scoring complete for assessment %s", assessment_id)

        result = {
            'scoring_status': 'done',
            'overall_score':  overall['overall_score'],
            'overall_level':  overall['overall_level'],
            'domains_scored': overall['domains_scored'],
            'kpis_scored':    len([k for k in kpi_scores.values() if not k['is_excluded']]),
            'kpis_excluded':  len([k for k in kpi_scores.values() if k['is_excluded']]),
        }

    except Exception as e:
        try:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE dg_toolkit.assessments SET scoring_status = 'failed' WHERE id = %s",
                    (assessment_id,),
                )
            conn.commit()
        except Exception:
            pass
        logger.error("Scoring failed for assessment %s: %s", assessment_id, e)
        raise

    finally:
        conn.close()

    # Chain → Layer 1 (uses its own connection)
    try:
        from app.services.layer1 import run_layer1
        run_layer1(assessment_id)
    except Exception as e:
        # layer1 already set layer2_status = 'failed' internally
        # scoring itself succeeded — do not re-raise
        logger.error("Layer 1 failed for assessment %s: %s", assessment_id, e)

    return result
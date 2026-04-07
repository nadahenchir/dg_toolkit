import sys
sys.path.insert(0, r'C:\Users\USER\OneDrive\Bureau\dg_toolkit\app\db')
from connection import get_connection, get_cursor
from datetime import datetime, timezone

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
# Step 1 — Compute KPI scores
# ------------------------------------------------------------
def compute_kpi_scores(assessment_id: int, cur) -> dict:
    """
    For each KPI:
    - If Q1 = N.A → excluded (is_excluded = True, raw_score = NULL)
    - If Q1 = Not → raw_score = 0.0, maturity_level = 1
    - Else → weighted average of non-hidden, non-NA answers
              weights renormalized if any question is N.A
    Returns dict of kpi_id -> {raw_score, maturity_level, is_excluded}
    """

    # Get KPI metadata (is_inverted) needed for scoring
    cur.execute("SELECT id, is_inverted FROM dg_toolkit.kpis")
    kpis = {k['id']: k for k in cur.fetchall()}

    # Get all answers for this assessment with question weights
    cur.execute("""
        SELECT a.question_id, a.is_na, a.is_hidden, a.raw_value,
               q.kpi_id, q.question_number, q.weight, q.is_gatekeeper
        FROM dg_toolkit.answers a
        JOIN dg_toolkit.questions q ON q.id = a.question_id
        WHERE a.assessment_id = %s
        ORDER BY q.kpi_id, q.question_number
    """, [assessment_id])
    answers = cur.fetchall()
    # Cast Decimal fields to float to avoid type errors
    answers = [dict(a) for a in answers]

    for a in answers:
        a['weight']    = float(a['weight'])
        a['raw_value'] = float(a['raw_value']) if a['raw_value'] is not None else None

    # Group answers by KPI
    kpi_answers = {}
    for a in answers:
        kid = a['kpi_id']
        if kid not in kpi_answers:
            kpi_answers[kid] = []
        kpi_answers[kid].append(a)

    kpi_scores = {}
    now = datetime.now(timezone.utc)

    for kpi_id, kpi_ans in kpi_answers.items():
        # Find Q1
        q1 = next((a for a in kpi_ans if a['question_number'] == 1), None)

        # Q1 = N.A → exclude KPI entirely
        if q1 and q1['is_na']:
            kpi_scores[kpi_id] = {
                'raw_score':      None,
                'maturity_level': None,
                'is_excluded':    True,
            }
            continue

        # Q1 = Not (0.0) → L1, no need to compute further
        if q1 and q1['raw_value'] == 0.0:
            kpi_scores[kpi_id] = {
                'raw_score':      0.0,
                'maturity_level': 1,
                'is_excluded':    False,
            }
            continue

        # Normal scoring — use non-hidden, non-NA answers
        scorable = [
            a for a in kpi_ans
            if not a['is_hidden'] and not a['is_na'] and a['raw_value'] is not None
        ]

        if not scorable:
            kpi_scores[kpi_id] = {
                'raw_score':      0.0,
                'maturity_level': 1,
                'is_excluded':    False,
            }
            continue

        # Renormalize weights for scorable questions
        total_weight = sum(float(a['weight']) for a in scorable)
        raw_score = sum(
            (float(a['weight'] / total_weight) * float(a['raw_value']))
            for a in scorable
        )

        # Handle inverted KPIs (lower = better)
        if kpis[kpi_id]['is_inverted']:
            raw_score = 1.0 - raw_score

        raw_score = round(raw_score, 4)
        maturity_level = resolve_maturity_level(raw_score)

        kpi_scores[kpi_id] = {
            'raw_score':      raw_score,
            'maturity_level': maturity_level,
            'is_excluded':    False,
        }

    # Insert into kpi_scores — delete first for idempotency
    cur.execute("""
        DELETE FROM dg_toolkit.kpi_scores WHERE assessment_id = %s
    """, [assessment_id])

    for kpi_id, score in kpi_scores.items():
        cur.execute("""
            INSERT INTO dg_toolkit.kpi_scores
                (assessment_id, kpi_id, raw_score, maturity_level, is_excluded, computed_at)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            assessment_id,
            kpi_id,
            score['raw_score'],
            score['maturity_level'],
            score['is_excluded'],
            now,
        ))

    return kpi_scores


# ------------------------------------------------------------
# Step 2 — Compute domain scores
# ------------------------------------------------------------
def compute_domain_scores(assessment_id: int, kpi_scores: dict, cur) -> dict:
    """
    For each domain:
    - Weighted average of non-excluded KPI scores
    - Copies target_level from domain_targets
    - Computes gap = target_level - maturity_level
    """

    # Get all KPIs with domain and weight
    cur.execute("""
        SELECT id, domain_id, weight, domain_order
        FROM dg_toolkit.kpis
        ORDER BY domain_id, domain_order
    """)
    kpis = cur.fetchall()

    # Get domain targets for this assessment
    cur.execute("""
        SELECT domain_id, target_level
        FROM dg_toolkit.domain_targets
        WHERE assessment_id = %s
    """, [assessment_id])
    targets = {t['domain_id']: t['target_level'] for t in cur.fetchall()}

    # Get domain weights
    cur.execute("SELECT id, weight FROM dg_toolkit.domains")
    domains = {d['id']: d['weight'] for d in cur.fetchall()}

    # Group KPIs by domain
    domain_kpis = {}
    for k in kpis:
        did = k['domain_id']
        if did not in domain_kpis:
            domain_kpis[did] = []
        domain_kpis[did].append(k)

    domain_scores = {}
    now = datetime.now(timezone.utc)

    for domain_id, d_kpis in domain_kpis.items():
        # Only score non-excluded KPIs
        scorable = [
            k for k in d_kpis
            if kpi_scores.get(k['id']) and not kpi_scores[k['id']]['is_excluded']
            and kpi_scores[k['id']]['raw_score'] is not None
        ]

        if not scorable:
            continue

        # Renormalize weights for scorable KPIs
        total_weight = sum(float(k['weight']) for k in scorable)
        raw_score = sum(
            (float(k['weight']) / total_weight * float(kpi_scores[k['id']]['raw_score']))
            for k in scorable
        )
        raw_score = round(raw_score, 4)
        maturity_level = resolve_maturity_level(raw_score)
        target_level = targets.get(domain_id)
        gap = (target_level - maturity_level) if target_level else None

        domain_scores[domain_id] = {
            'raw_score':      raw_score,
            'maturity_level': maturity_level,
            'target_level':   target_level,
            'gap':            gap,
            'kpis_scored':    len(scorable),
        }

    # Insert into domain_scores — delete first for idempotency
    cur.execute("""
        DELETE FROM dg_toolkit.domain_scores WHERE assessment_id = %s
    """, [assessment_id])

    for domain_id, score in domain_scores.items():
        cur.execute("""
            INSERT INTO dg_toolkit.domain_scores
                (assessment_id, domain_id, raw_score, maturity_level,
                 target_level, gap, kpis_scored, computed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            assessment_id,
            domain_id,
            score['raw_score'],
            score['maturity_level'],
            score['target_level'],
            score['gap'],
            score['kpis_scored'],
            now,
        ))

    return domain_scores


# ------------------------------------------------------------
# Step 3 — Compute overall assessment score
# ------------------------------------------------------------
def compute_assessment_score(assessment_id: int, domain_scores: dict, cur):
    """
    Weighted average of all domain scores.
    """

    # Get domain weights
    cur.execute("SELECT id, weight FROM dg_toolkit.domains")
    domain_weights = {d['id']: d['weight'] for d in cur.fetchall()}

    scorable_domains = {
        did: s for did, s in domain_scores.items()
        if s['raw_score'] is not None
    }

    if not scorable_domains:
        return None

    # Renormalize weights
    total_weight = sum(float(domain_weights[did]) for did in scorable_domains)
    overall_score = sum(
        (float(domain_weights[did]) / total_weight) * float(scorable_domains[did]['raw_score'])
        for did in scorable_domains
    )
    overall_score  = round(overall_score, 4)
    overall_level  = resolve_maturity_level(overall_score)
    domains_scored = len(scorable_domains)
    now            = datetime.now(timezone.utc)

    # Delete and reinsert
    cur.execute("""
        DELETE FROM dg_toolkit.assessment_scores WHERE assessment_id = %s
    """, [assessment_id])

    cur.execute("""
        INSERT INTO dg_toolkit.assessment_scores
            (assessment_id, overall_score, overall_level, domains_scored, computed_at)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING overall_score, overall_level, domains_scored
    """, (assessment_id, overall_score, overall_level, domains_scored, now))

    return cur.fetchone()


# ------------------------------------------------------------
# Main entry point — called from submit route
# ------------------------------------------------------------
def run_scoring(assessment_id: int):
    """
    Full scoring pipeline:
    kpi_scores → domain_scores → assessment_scores
    Updates assessments.scoring_status throughout.
    """
    conn = get_connection()
    cur  = get_cursor(conn)

    try:
        # Mark scoring as running
        cur.execute("""
            UPDATE dg_toolkit.assessments
            SET scoring_status = 'running'
            WHERE id = %s
        """, [assessment_id])
        conn.commit()

        # Step 1
        kpi_scores = compute_kpi_scores(assessment_id, cur)

        # Step 2
        domain_scores = compute_domain_scores(assessment_id, kpi_scores, cur)

        # Step 3
        overall = compute_assessment_score(assessment_id, domain_scores, cur)

        # Mark done
        cur.execute("""
            UPDATE dg_toolkit.assessments
            SET scoring_status = 'done',
                scored_at = NOW(),
                status = 'complete'
            WHERE id = %s
        """, [assessment_id])
        conn.commit()

        return {
            'scoring_status': 'done',
            'overall_score':  overall['overall_score'],
            'overall_level':  overall['overall_level'],
            'domains_scored': overall['domains_scored'],
            'kpis_scored':    len([k for k in kpi_scores.values() if not k['is_excluded']]),
            'kpis_excluded':  len([k for k in kpi_scores.values() if k['is_excluded']]),
        }

    except Exception as e:
        conn.rollback()
        cur.execute("""
            UPDATE dg_toolkit.assessments
            SET scoring_status = 'failed'
            WHERE id = %s
        """, [assessment_id])
        conn.commit()
        raise e
    finally:
        cur.close()
        conn.close()
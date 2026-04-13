"""
scripts/seed_assessments.py
-----------------------------
Generates realistic fake assessments for all organizations
that don't already have a completed assessment.

For each org:
1. Creates assessment
2. Generates realistic domain + KPI scores based on industry
3. Inserts assessment_scores, domain_scores, kpi_scores
4. Runs Layer 1 to generate recommendations
5. Auto-rates recommendations realistically
6. Sets layer2_status = 'done'

Run from project root:
    python scripts/seed_assessments.py
"""

import logging
import sys
import os
import random

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.connection import get_connection

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# ── industry maturity profiles ────────────────────────────────
# (overall_min, overall_max, domain_strengths, domain_weaknesses)
# domain ids: 1=Governance 2=Quality 3=Metadata 4=Security
#             5=MasterData 6=Architecture 7=Integration 8=BI
#             9=DataModeling 10=Storage 11=Documents

INDUSTRY_PROFILES = {
    "Banking": {
        "overall": (2, 3),
        "strong":  {2: 3, 4: 3, 5: 3, 1: 3},   # Quality, Security, Master, Governance
        "weak":    {11: 1, 6: 2, 3: 2},           # Documents, Architecture, Metadata
    },
    "Insurance": {
        "overall": (2, 3),
        "strong":  {4: 3, 2: 3, 1: 2},
        "weak":    {5: 1, 8: 1, 11: 1},
    },
    "Telecom": {
        "overall": (3, 4),
        "strong":  {6: 4, 7: 4, 8: 3, 2: 3},
        "weak":    {11: 2, 1: 2},
    },
    "Energy": {
        "overall": (2, 2),
        "strong":  {10: 3, 4: 3},
        "weak":    {8: 1, 3: 1, 11: 1},
    },
    "Retail": {
        "overall": (2, 2),
        "strong":  {8: 3, 5: 3},
        "weak":    {6: 1, 11: 1, 3: 1},
    },
    "Healthcare": {
        "overall": (1, 2),
        "strong":  {4: 2, 11: 2},
        "weak":    {8: 1, 6: 1, 7: 1},
    },
    "Public Sector": {
        "overall": (1, 2),
        "strong":  {11: 2, 4: 2},
        "weak":    {8: 1, 7: 1, 6: 1},
    },
    "Industrial": {
        "overall": (2, 2),
        "strong":  {10: 3, 7: 2},
        "weak":    {8: 1, 3: 1, 11: 1},
    },
    "Other": {
        "overall": (2, 3),
        "strong":  {2: 3, 1: 2},
        "weak":    {11: 1, 6: 1},
    },
}

# domain id → target level (consultants always set ambitious targets)
def get_target_level(maturity_level: int) -> int:
    return min(5, maturity_level + random.choice([1, 2]))


def get_domain_maturity(domain_id: int, profile: dict, overall_level: int) -> int:
    if domain_id in profile["strong"]:
        return min(5, profile["strong"][domain_id] + random.randint(-1, 1))
    if domain_id in profile["weak"]:
        return max(1, profile["weak"][domain_id] + random.randint(0, 1))
    # default: close to overall level with some variance
    return max(1, min(5, overall_level + random.randint(-1, 1)))


def maturity_to_score(level: int) -> float:
    mapping = {1: 0.15, 2: 0.35, 3: 0.55, 4: 0.75, 5: 0.90}
    return mapping.get(level, 0.35)


def score_to_level(score: float) -> int:
    if score <= 0.20: return 1
    if score <= 0.40: return 2
    if score <= 0.60: return 3
    if score <= 0.80: return 4
    return 5


# ── KPI ratings by domain ────────────────────────────────────
# which KPIs tend to get implemented and rated highly
# based on domain strength in each industry

HIGHLY_RATED_KPIS = {
    "Banking":      [1, 2, 4, 11, 12, 20, 21, 24],
    "Insurance":    [2, 11, 14, 20, 21, 47, 49],
    "Telecom":      [1, 4, 5, 11, 28, 33, 38, 41],
    "Energy":       [1, 11, 20, 47, 48, 49, 50],
    "Retail":       [1, 11, 24, 25, 38, 41, 42],
    "Healthcare":   [2, 4, 11, 20, 47, 51, 52],
    "Public Sector":[1, 11, 20, 47, 51, 52, 53],
    "Industrial":   [1, 6, 7, 11, 33, 47, 50],
    "Other":        [1, 2, 4, 11, 16, 28, 38],
}


def seed_assessments():
    conn = get_connection()
    try:
        # fetch orgs that don't have a completed assessment yet
        with conn.cursor() as cur:
            cur.execute("""
                SELECT o.id, o.name, o.industry, o.size_band
                FROM dg_toolkit.organizations o
                WHERE o.deleted_at IS NULL
                AND o.id NOT IN (
                    SELECT DISTINCT organization_id
                    FROM dg_toolkit.assessments
                    WHERE deleted_at IS NULL
                    AND layer2_status = 'done'
                )
                ORDER BY o.id
            """)
            orgs = cur.fetchall()

        logger.info(f"Found {len(orgs)} organizations without completed assessments\n")

        # fetch all KPIs
        with conn.cursor() as cur:
            cur.execute("SELECT id, domain_id FROM dg_toolkit.kpis ORDER BY id")
            all_kpis = cur.fetchall()

        # fetch action library
        with conn.cursor() as cur:
            cur.execute("SELECT id, kpi_id, from_level, impact, effort FROM dg_toolkit.action_library")
            action_rows = cur.fetchall()

        # build action lookup: (kpi_id, from_level) -> action
        action_lookup = {}
        for (action_id, kpi_id, from_level, impact, effort) in action_rows:
            action_lookup[(kpi_id, from_level)] = (action_id, impact, effort)

        success = 0
        failed  = 0

        for (org_id, org_name, industry, size_band) in orgs:
            try:
                logger.info(f"Processing: {org_name} ({industry}, {size_band})")

                profile      = INDUSTRY_PROFILES.get(industry, INDUSTRY_PROFILES["Other"])
                overall_min, overall_max = profile["overall"]
                overall_level = random.randint(overall_min, overall_max)
                overall_score = maturity_to_score(overall_level) + random.uniform(-0.05, 0.05)

                # ── create assessment ─────────────────────────
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO dg_toolkit.assessments
                            (organization_id, consultant_id, status, scoring_status,
                             layer2_status, layer3_status, targets_locked,
                             submitted_at, scored_at)
                        VALUES (%s, 2, 'complete', 'done', 'done', 'done', true,
                                now() - (random() * 180 || ' days')::interval,
                                now() - (random() * 180 || ' days')::interval)
                        RETURNING id
                    """, (org_id,))
                    assessment_id = cur.fetchone()[0]

                # ── domain scores ─────────────────────────────
                domain_levels = {}
                for domain_id in range(1, 12):
                    level  = get_domain_maturity(domain_id, profile, overall_level)
                    target = get_target_level(level)
                    score  = maturity_to_score(level) + random.uniform(-0.03, 0.03)
                    domain_levels[domain_id] = level

                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO dg_toolkit.domain_scores
                                (assessment_id, domain_id, raw_score, maturity_level,
                                 target_level, gap, kpis_scored, computed_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, now())
                        """, (assessment_id, domain_id, round(score, 4), level,
                              target, target - level, random.randint(3, 5)))

                # ── assessment score ──────────────────────────
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO dg_toolkit.assessment_scores
                            (assessment_id, overall_score, overall_level,
                             domains_scored, computed_at)
                        VALUES (%s, %s, %s, 11, now())
                    """, (assessment_id, round(overall_score, 4), overall_level))

                # ── kpi scores + recommendations ──────────────
                highly_rated = HIGHLY_RATED_KPIS.get(industry, HIGHLY_RATED_KPIS["Other"])

                for (kpi_id, domain_id) in all_kpis:
                    kpi_level = domain_levels.get(domain_id, overall_level)
                    kpi_score = maturity_to_score(kpi_level) + random.uniform(-0.05, 0.05)

                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO dg_toolkit.kpi_scores
                                (assessment_id, kpi_id, raw_score, maturity_level,
                                 is_excluded, computed_at)
                            VALUES (%s, %s, %s, %s, false, now())
                        """, (assessment_id, kpi_id, round(kpi_score, 4), kpi_level))

                    # only add recommendation if not at max level
                    if kpi_level < 5:
                        action = action_lookup.get((kpi_id, kpi_level))
                        if not action:
                            # try lower level
                            action = action_lookup.get((kpi_id, max(1, kpi_level - 1)))
                        if not action:
                            continue

                        action_id, impact, effort = action
                        action_category = (
                            "Quick Win"  if impact == "High" and effort == "Low"  else
                            "Strategic"  if impact == "High" and effort == "High" else
                            "Fill In"
                        )

                        # determine rating
                        was_implemented     = kpi_id in highly_rated
                        implementation_rating = None
                        rated_at            = None

                        if was_implemented:
                            # highly rated KPIs get 4 or 5 stars
                            implementation_rating = random.choices([4, 5], weights=[0.3, 0.7])[0]
                            rated_at = "now() - (random() * 60 || ' days')::interval"

                        with conn.cursor() as cur:
                            if was_implemented:
                                cur.execute(f"""
                                    INSERT INTO dg_toolkit.recommendations
                                        (assessment_id, kpi_id, base_action_id, priority_score,
                                         action_category, was_implemented, implementation_rating,
                                         rated_at)
                                    VALUES (%s, %s, %s, 1.0, %s, true, %s, {rated_at})
                                """, (assessment_id, kpi_id, action_id,
                                      action_category, implementation_rating))
                            else:
                                cur.execute("""
                                    INSERT INTO dg_toolkit.recommendations
                                        (assessment_id, kpi_id, base_action_id, priority_score,
                                         action_category)
                                    VALUES (%s, %s, %s, 1.0, %s)
                                """, (assessment_id, kpi_id, action_id, action_category))

                # ── domain targets ────────────────────────────
                for domain_id in range(1, 12):
                    level  = domain_levels[domain_id]
                    target = get_target_level(level)
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO dg_toolkit.domain_targets
                                (assessment_id, domain_id, target_level)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (assessment_id, domain_id) DO NOTHING
                        """, (assessment_id, domain_id, target))

                conn.commit()
                logger.info(f"  ✓ Assessment {assessment_id} created (overall L{overall_level})")
                success += 1

            except Exception as e:
                logger.error(f"  ✗ Failed for {org_name}: {e}")
                conn.rollback()
                failed += 1

        logger.info(f"\nDone. Success: {success} | Failed: {failed}")

    finally:
        conn.close()


if __name__ == "__main__":
    seed_assessments()
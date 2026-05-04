"""
seed_test_assessments.py
------------------------
Seeds 20 test assessments for Tunisian companies via the DG Toolkit API.
Covers all hard cases: gap=0, above target, below target, mixed per domain.

Usage:
    python seed_test_assessments.py

Requirements:
    pip install requests

Config:
    Set CONSULTANT_PASSWORD below before running.
    Make sure your Flask server is running.
"""

import requests
import time
import json

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL             = "http://localhost:5000/api"
CONSULTANT_ID        = 3
CONSULTANT_EMAIL     = "emnakallel@kpmg.com"
CONSULTANT_PASSWORD  = "test123"   # ← replace this
ENGAGEMENT_DATE      = "2026-05-04"

# Persistent session — carries auth cookie across all requests
SESSION = requests.Session()

# ── Domain IDs ────────────────────────────────────────────────────────────────
DOMAIN_IDS = list(range(1, 12))

# ── KPI IDs per domain ────────────────────────────────────────────────────────
KPIS_BY_DOMAIN = {
    1:  [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    2:  [11, 12, 13, 14, 15],
    3:  [16, 17, 18, 19],
    4:  [20, 21, 22, 23],
    5:  [24, 25, 26, 27],
    6:  [28, 29, 30, 31, 32],
    7:  [33, 34, 35, 36, 37],
    8:  [38, 39, 40, 41, 42],
    9:  [43, 44, 45, 46],
    10: [47, 48, 49, 50],
    11: [51, 52, 53],
}

# ── Question IDs ──────────────────────────────────────────────────────────────
# Questions start at ID 213, 4 per KPI
# KPI 1 → 213-216 | KPI 2 → 217-220 | etc.
def get_question_ids(kpi_id):
    base = (kpi_id - 1) * 4 + 213
    return [base, base + 1, base + 2, base + 3]


# ── Maturity level → answer pattern (normal KPIs) ────────────────────────────
# Gate triggers on Q1="Not" → L1 only needs Q1
LEVEL_TO_ANSWERS = {
    1: {"q1": "Not",       "q2": None,    "q3": None,    "q4": None},
    2: {"q1": "Slightly",  "q2": "Not",   "q3": "Not",   "q4": "Not"},
    3: {"q1": "Partially", "q2": "Fully", "q3": "Not",   "q4": "Not"},
    4: {"q1": "Mostly",    "q2": "Fully", "q3": "Fully", "q4": "Not"},
    5: {"q1": "Fully",     "q2": "Fully", "q3": "Fully", "q4": "Fully"},
}

# ── Maturity level → answer pattern (inverted KPIs: 25, 34) ──────────────────
# Gate triggers on Q1="Fully" → L1 only needs Q1
LEVEL_TO_ANSWERS_INVERTED = {
    1: {"q1": "Fully",     "q2": None,    "q3": None,    "q4": None},
    2: {"q1": "Mostly",    "q2": "Fully", "q3": "Fully", "q4": "Fully"},
    3: {"q1": "Partially", "q2": "Not",   "q3": "Fully", "q4": "Fully"},
    4: {"q1": "Slightly",  "q2": "Not",   "q3": "Not",   "q4": "Fully"},
    5: {"q1": "Not",       "q2": "Not",   "q3": "Not",   "q4": "Not"},
}

INVERTED_KPI_IDS = {25, 34}


def build_kpi_answers(kpi_id: int, maturity_level: int) -> dict:
    q_ids   = get_question_ids(kpi_id)
    mapping = LEVEL_TO_ANSWERS_INVERTED if kpi_id in INVERTED_KPI_IDS else LEVEL_TO_ANSWERS
    pattern = mapping[maturity_level]
    answers = [{"question_id": q_ids[0], "selected_option": pattern["q1"]}]
    if pattern["q2"] is not None:
        answers.append({"question_id": q_ids[1], "selected_option": pattern["q2"]})
        answers.append({"question_id": q_ids[2], "selected_option": pattern["q3"]})
        answers.append({"question_id": q_ids[3], "selected_option": pattern["q4"]})
    return {"answers": answers}


# ── 20 Test Companies ─────────────────────────────────────────────────────────
COMPANIES = [
    {"org": {"name": "Banque Nationale Agricole", "industry": "Banking", "industry_other": None, "country": "Tunisia", "size_band": "Large"},
     "targets": [3,3,3,3,3,3,3,3,3,3,3], "domain_levels": [3,3,3,3,3,3,3,3,3,3,3],
     "label": "Gap=0 everywhere (banking large)"},

    {"org": {"name": "Attijari Bank", "industry": "Banking", "industry_other": None, "country": "Tunisia", "size_band": "Large"},
     "targets": [4,4,4,4,4,4,4,4,4,4,4], "domain_levels": [4,4,4,4,4,4,4,4,4,4,4],
     "label": "At target L4 everywhere"},

    {"org": {"name": "Banque Internationale Arabe de Tunisie", "industry": "Banking", "industry_other": None, "country": "Tunisia", "size_band": "Enterprise"},
     "targets": [4,4,4,4,4,4,4,4,4,4,4], "domain_levels": [5,5,5,5,5,5,5,5,5,5,5],
     "label": "L5 exceeds L4 target everywhere"},

    {"org": {"name": "Tunisie Telecom", "industry": "Telecom", "industry_other": None, "country": "Tunisia", "size_band": "Enterprise"},
     "targets": [4,4,4,4,4,4,4,4,4,4,4], "domain_levels": [2,4,2,4,2,4,2,4,2,4,2],
     "label": "Alternating L2/L4 vs L4 target (mixed)"},

    {"org": {"name": "Ooredoo Tunisie", "industry": "Telecom", "industry_other": None, "country": "Tunisia", "size_band": "Large"},
     "targets": [3,3,3,3,3,3,3,3,3,3,3], "domain_levels": [4,2,4,2,4,2,4,2,4,2,4],
     "label": "Alternating L4/L2 vs L3 target (some above, some below)"},

    {"org": {"name": "STAR Assurances", "industry": "Insurance", "industry_other": None, "country": "Tunisia", "size_band": "Large"},
     "targets": [3,3,3,3,3,3,3,3,3,3,3], "domain_levels": [1,1,1,1,1,1,1,1,1,1,1],
     "label": "L1 everywhere vs L3 target (insurance large)"},

    {"org": {"name": "GAT Assurances", "industry": "Insurance", "industry_other": None, "country": "Tunisia", "size_band": "SME"},
     "targets": [2,2,2,2,2,2,2,2,2,2,2], "domain_levels": [2,2,2,2,2,2,2,2,2,2,2],
     "label": "Gap=0 everywhere at L2 (insurance SME)"},

    {"org": {"name": "Societe Tunisienne de l Electricite et du Gaz", "industry": "Energy", "industry_other": None, "country": "Tunisia", "size_band": "Enterprise"},
     "targets": [4,4,4,4,4,4,4,4,4,4,4], "domain_levels": [3,3,3,3,3,3,3,3,3,3,3],
     "label": "Consistent gap of 1 everywhere (energy enterprise)"},

    {"org": {"name": "Societe Nationale d Exploitation et de Distribution des Eaux", "industry": "Public Sector", "industry_other": None, "country": "Tunisia", "size_band": "Large"},
     "targets": [3,3,3,3,3,3,3,3,3,3,3], "domain_levels": [1,2,1,2,1,2,1,2,1,2,1],
     "label": "L1/L2 mixed vs L3 target (public sector)"},

    {"org": {"name": "Poulina Group Holding", "industry": "Industrial", "industry_other": None, "country": "Tunisia", "size_band": "Enterprise"},
     "targets": [4,4,4,4,4,4,4,4,4,4,4], "domain_levels": [2,3,2,3,2,3,2,3,2,3,2],
     "label": "L2/L3 mixed vs L4 target (industrial enterprise)"},

    {"org": {"name": "Delice Holding", "industry": "Retail", "industry_other": None, "country": "Tunisia", "size_band": "Large"},
     "targets": [3,3,3,3,3,3,3,3,3,3,3], "domain_levels": [3,3,3,3,3,3,3,3,3,3,3],
     "label": "Gap=0 everywhere at L3 (retail large)"},

    {"org": {"name": "Tunisair", "industry": "Other", "industry_other": "Aviation", "country": "Tunisia", "size_band": "Large"},
     "targets": [3,3,3,3,3,3,3,3,3,3,3], "domain_levels": [1,1,1,1,1,1,1,1,1,1,1],
     "label": "L1 everywhere vs L3 target (aviation)"},

    {"org": {"name": "TOPNET", "industry": "Telecom", "industry_other": None, "country": "Tunisia", "size_band": "SME"},
     "targets": [2,2,2,2,2,2,2,2,2,2,2], "domain_levels": [2,2,2,2,2,2,2,2,2,2,2],
     "label": "Gap=0 at L2 (telecom SME)"},

    {"org": {"name": "Vermeg", "industry": "Other", "industry_other": "FinTech", "country": "Tunisia", "size_band": "SME"},
     "targets": [4,4,4,4,4,4,4,4,4,4,4], "domain_levels": [3,4,3,4,3,4,3,4,3,4,3],
     "label": "L3/L4 mixed vs L4 target (fintech SME near target)"},

    {"org": {"name": "Telnet Holding", "industry": "Other", "industry_other": "IT Services", "country": "Tunisia", "size_band": "SME"},
     "targets": [4,4,4,4,4,4,4,4,4,4,4], "domain_levels": [2,2,2,2,2,2,2,2,2,2,2],
     "label": "L2 everywhere vs L4 target (IT SME high ambition)"},

    {"org": {"name": "Union Internationale de Banques", "industry": "Banking", "industry_other": None, "country": "Tunisia", "size_band": "Large"},
     "targets": [4,4,4,4,4,4,4,4,4,4,4], "domain_levels": [3,5,3,5,3,5,3,5,3,5,3],
     "label": "L3/L5 mixed vs L4 target (some below, some above)"},

    {"org": {"name": "Amen Bank", "industry": "Banking", "industry_other": None, "country": "Tunisia", "size_band": "Large"},
     "targets": [3,3,3,3,3,3,3,3,3,3,3], "domain_levels": [4,5,4,5,4,5,4,5,4,5,4],
     "label": "L4/L5 everywhere vs L3 target (exceeds everywhere)"},

    {"org": {"name": "Caisse Nationale d Assurance Maladie", "industry": "Healthcare", "industry_other": None, "country": "Tunisia", "size_band": "Large"},
     "targets": [3,3,3,3,3,3,3,3,3,3,3], "domain_levels": [1,1,1,1,1,1,1,1,1,1,1],
     "label": "L1 everywhere vs L3 target (public healthcare)"},

    {"org": {"name": "Richbond Tunisie", "industry": "Industrial", "industry_other": None, "country": "Tunisia", "size_band": "Large"},
     "targets": [2,2,2,2,2,2,2,2,2,2,2], "domain_levels": [3,3,3,3,3,3,3,3,3,3,3],
     "label": "L3 everywhere vs L2 target (manufacturing above target)"},

    {"org": {"name": "Carthage Cement", "industry": "Industrial", "industry_other": None, "country": "Tunisia", "size_band": "Large"},
     "targets": [3,3,3,3,3,3,3,3,3,3,3], "domain_levels": [2,2,2,2,2,2,2,2,2,2,2],
     "label": "L2 everywhere vs L3 target (industrial consistent gap 1)"},
]


# ── Auth ──────────────────────────────────────────────────────────────────────

def login():
    r = SESSION.post(f"{BASE_URL}/auth/login", json={
        "email":    CONSULTANT_EMAIL,
        "password": CONSULTANT_PASSWORD,
    })
    if not r.ok:
        raise RuntimeError(
            f"Login failed: {r.status_code} {r.text}\n"
            "→ Check CONSULTANT_EMAIL and CONSULTANT_PASSWORD at the top of this script."
        )
    data = r.json()
    print(f"  ✓ Logged in as '{data.get('consultant_name')}' (id={data.get('consultant_id')})")


# ── API helpers ───────────────────────────────────────────────────────────────

def create_org(org_data):
    r = SESSION.post(f"{BASE_URL}/organizations", json=org_data)
    if not r.ok:
        raise RuntimeError(f"Create org failed: {r.status_code} {r.text}")
    return r.json()["id"]


def create_assessment(org_id):
    r = SESSION.post(f"{BASE_URL}/assessments", json={
        "organization_id": org_id,
        "consultant_id":   CONSULTANT_ID,
        "engagement_date": ENGAGEMENT_DATE,
    })
    if not r.ok:
        raise RuntimeError(f"Create assessment failed: {r.status_code} {r.text}")
    return r.json()["id"]


def set_targets(assessment_id, targets):
    r = SESSION.post(f"{BASE_URL}/assessments/{assessment_id}/targets", json={
        "targets": [{"domain_id": i + 1, "target_level": targets[i]} for i in range(11)]
    })
    if not r.ok:
        raise RuntimeError(f"Set targets failed: {r.status_code} {r.text}")


def start_assessment(assessment_id):
    r = SESSION.post(f"{BASE_URL}/assessments/{assessment_id}/start")
    if not r.ok:
        raise RuntimeError(f"Start assessment failed: {r.status_code} {r.text}")


def submit_kpi_answers(assessment_id, kpi_id, maturity_level):
    r = SESSION.post(
        f"{BASE_URL}/assessments/{assessment_id}/answers/kpi/{kpi_id}",
        json=build_kpi_answers(kpi_id, maturity_level)
    )
    if not r.ok:
        raise RuntimeError(f"Answers KPI {kpi_id} failed: {r.status_code} {r.text}")


def submit_assessment(assessment_id):
    r = SESSION.post(f"{BASE_URL}/assessments/{assessment_id}/submit")
    if not r.ok:
        raise RuntimeError(f"Submit failed: {r.status_code} {r.text}")
    return r.json()


# ── Main ──────────────────────────────────────────────────────────────────────

def seed():
    print("=" * 60)
    print("DG Toolkit — Test Assessment Seeder")
    print("=" * 60)

    login()

    results = []

    for i, company in enumerate(COMPANIES[5:6] + COMPANIES[8:9] + COMPANIES[11:12] + COMPANIES[17:18], 1):
        name  = company["org"]["name"]
        label = company["label"]
        print(f"\n[{i:02d}/20] {name}")
        print(f"         {label}")

        try:
            org_id = create_org(company["org"])
            print(f"         org_id={org_id}")

            assessment_id = create_assessment(org_id)
            print(f"         assessment_id={assessment_id}")

            set_targets(assessment_id, company["targets"])
            print(f"         targets={company['targets']}")

            start_assessment(assessment_id)
            print(f"         assessment started")

            for domain_idx, domain_id in enumerate(DOMAIN_IDS):
                level = company["domain_levels"][domain_idx]
                for kpi_id in KPIS_BY_DOMAIN[domain_id]:
                    submit_kpi_answers(assessment_id, kpi_id, level)
            print(f"         all 53 KPIs answered")

            result = submit_assessment(assessment_id)
            print(f"         ✓ scored — overall_level=L{result.get('overall_level', '?')}")

            results.append({"company": name, "org_id": org_id,
                             "assessment_id": assessment_id, "status": "ok", "label": label})
            time.sleep(2)

        except Exception as e:
            print(f"         ✗ FAILED: {e}")
            results.append({"company": name, "status": "failed", "error": str(e)})

    print("\n" + "=" * 60)
    print("SEED COMPLETE")
    print("=" * 60)
    ok     = [r for r in results if r["status"] == "ok"]
    failed = [r for r in results if r["status"] == "failed"]
    print(f"  Succeeded: {len(ok)}/20")
    print(f"  Failed:    {len(failed)}/20")

    if ok:
        print("\n  Assessment IDs created:")
        for r in ok:
            print(f"    [{r['assessment_id']:3d}] {r['company']}")

    if failed:
        print("\n  Failures:")
        for r in failed:
            print(f"    {r['company']}: {r['error']}")

    with open("seed_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print("\n  Full results saved to seed_results.json")


if __name__ == "__main__":
    seed()
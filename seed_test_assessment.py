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
    Set BASE_URL, LOGIN_EMAIL, and LOGIN_PASSWORD at the top of this file.
    Make sure your Flask server is running before executing.
"""

import requests
import time
import json

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL       = "http://localhost:5000/api"
LOGIN_EMAIL    = "emnakallel@kpmg.com"
LOGIN_PASSWORD = "test123"
ENGAGEMENT_DATE = "2026-05-04"

# ── Domain IDs ────────────────────────────────────────────────────────────────
# 1  Data Governance
# 2  Data Quality
# 3  Metadata Management
# 4  Data Security
# 5  Master & Reference Data
# 6  Data Architecture
# 7  Data Integration & Interoperability
# 8  Data Warehousing & BI
# 9  Data Modeling & Design
# 10 Data Storage & Operations
# 11 Document & Content Management

DOMAIN_IDS = list(range(1, 12))  # 1..11

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

# ── Answer option → maturity level mapping ────────────────────────────────────
# Normal KPIs: gate triggers on Q1="Not" → hides Q2-Q4 → L1
LEVEL_TO_ANSWERS = {
    1: {"q1": "Not",       "q2": None,    "q3": None,    "q4": None},
    2: {"q1": "Slightly",  "q2": "Not",   "q3": "Not",   "q4": "Not"},
    3: {"q1": "Partially", "q2": "Fully", "q3": "Not",   "q4": "Not"},
    4: {"q1": "Mostly",    "q2": "Fully", "q3": "Fully", "q4": "Not"},
    5: {"q1": "Fully",     "q2": "Fully", "q3": "Fully", "q4": "Fully"},
}

# Inverted KPIs: gate triggers on Q1="Fully" instead of "Not".
# Patterns are designed to produce the matching maturity level after inversion
# (raw_score = 1 - weighted_avg), assuming equal question weights (0.25 each).
INVERTED_LEVEL_TO_ANSWERS = {
    1: {"q1": "Fully",     "q2": None,    "q3": None,    "q4": None},
    2: {"q1": "Mostly",    "q2": "Fully", "q3": "Fully", "q4": "Fully"},
    3: {"q1": "Partially", "q2": "Mostly","q3": "Not",   "q4": "Not"},
    4: {"q1": "Slightly",  "q2": "Not",   "q3": "Not",   "q4": "Not"},
    5: {"q1": "Not",       "q2": "Not",   "q3": "Not",   "q4": "Not"},
}


def build_kpi_answers(kpi_id: int, maturity_level: int, kpi_map: dict) -> dict:
    """Build the answers payload for a single KPI to achieve the target maturity level."""
    kpi_data    = kpi_map[kpi_id]
    q_ids       = kpi_data["q_ids"]
    is_inverted = kpi_data["is_inverted"]

    pattern = INVERTED_LEVEL_TO_ANSWERS[maturity_level] if is_inverted else LEVEL_TO_ANSWERS[maturity_level]

    answers = [{"question_id": q_ids[0], "selected_option": pattern["q1"]}]

    # If gate triggered (L1), only Q1 is needed — backend hides Q2/Q3/Q4
    if pattern["q2"] is not None:
        answers.append({"question_id": q_ids[1], "selected_option": pattern["q2"]})
        answers.append({"question_id": q_ids[2], "selected_option": pattern["q3"]})
        answers.append({"question_id": q_ids[3], "selected_option": pattern["q4"]})

    return {"answers": answers}


# ── 20 Test Companies ─────────────────────────────────────────────────────────
# domain_levels: list of 11 maturity levels, one per domain (in order 1..11)
# targets:       list of 11 target levels, one per domain (in order 1..11)
#
# Hard cases:
#   - All equal & gap=0 everywhere         → BNA, GAT, Délice, TOPNET
#   - All above target everywhere          → BIAT, Amen Bank, Richbond
#   - All below target, large gap          → STAR, Tunisair, CNAM, Telnet
#   - Mixed: some above, some below        → Ooredoo, UIB
#   - Consistent gap of 1 everywhere      → STEG
#   - High ambition SME                    → Vermeg
#   - Multi-domain variance                → Poulina, Tunisie Telecom, SONEDE

COMPANIES = [
    # ── 1. BNA — Banking Large — Gap=0 everywhere ──────────────────────────
    {
        "org": {
            "name": "Banque Nationale Agricole",
            "industry": "Banking",
            "industry_other": None,
            "country": "Tunisia",
            "size_band": "Large",
        },
        "targets":       [3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3],
        "domain_levels": [3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3],
        "label": "Gap=0 everywhere (banking large)",
    },

    # ── 2. Attijari Bank — Banking Large — At target everywhere ───────────
    {
        "org": {
            "name": "Attijari Bank",
            "industry": "Banking",
            "industry_other": None,
            "country": "Tunisia",
            "size_band": "Large",
        },
        "targets":       [4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4],
        "domain_levels": [4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4],
        "label": "At target L4 everywhere",
    },

    # ── 3. BIAT — Banking Enterprise — Exceeds target everywhere ──────────
    {
        "org": {
            "name": "Banque Internationale Arabe de Tunisie",
            "industry": "Banking",
            "industry_other": None,
            "country": "Tunisia",
            "size_band": "Enterprise",
        },
        "targets":       [4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4],
        "domain_levels": [5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5],
        "label": "L5 exceeds L4 target everywhere",
    },

    # ── 4. Tunisie Telecom — Telecom Enterprise — Mixed gaps ──────────────
    {
        "org": {
            "name": "Tunisie Telecom",
            "industry": "Telecom",
            "industry_other": None,
            "country": "Tunisia",
            "size_band": "Enterprise",
        },
        "targets":       [4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4],
        "domain_levels": [2, 4, 2, 4, 2, 4, 2, 4, 2, 4, 2],
        "label": "Alternating L2/L4 vs L4 target (mixed)",
    },

    # ── 5. Ooredoo — Telecom Large — Above target on some, below on others
    {
        "org": {
            "name": "Ooredoo Tunisie",
            "industry": "Telecom",
            "industry_other": None,
            "country": "Tunisia",
            "size_band": "Large",
        },
        "targets":       [3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3],
        "domain_levels": [4, 2, 4, 2, 4, 2, 4, 2, 4, 2, 4],
        "label": "Alternating L4/L2 vs L3 target (some above, some below)",
    },

    # ── 6. STAR Assurances — Insurance Large — L1 everywhere, L3 target ──
    {
        "org": {
            "name": "STAR Assurances",
            "industry": "Insurance",
            "industry_other": None,
            "country": "Tunisia",
            "size_band": "Large",
        },
        "targets":       [3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3],
        "domain_levels": [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
        "label": "L1 everywhere vs L3 target (insurance large)",
    },

    # ── 7. GAT Assurances — Insurance SME — Gap=0 at L2 ──────────────────
    {
        "org": {
            "name": "GAT Assurances",
            "industry": "Insurance",
            "industry_other": None,
            "country": "Tunisia",
            "size_band": "SME",
        },
        "targets":       [2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2],
        "domain_levels": [2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2],
        "label": "Gap=0 everywhere at L2 (insurance SME)",
    },

    # ── 8. STEG — Energy Enterprise — Consistent gap of 1 ────────────────
    {
        "org": {
            "name": "Société Tunisienne de l'Electricité et du Gaz",
            "industry": "Energy",
            "industry_other": None,
            "country": "Tunisia",
            "size_band": "Enterprise",
        },
        "targets":       [4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4],
        "domain_levels": [3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3],
        "label": "Consistent gap of 1 everywhere (energy enterprise)",
    },

    # ── 9. SONEDE — Public Sector Large — L1-L2 mixed, L3 target ─────────
    {
        "org": {
            "name": "Société Nationale d'Exploitation et de Distribution des Eaux",
            "industry": "Public Sector",
            "industry_other": None,
            "country": "Tunisia",
            "size_band": "Large",
        },
        "targets":       [3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3],
        "domain_levels": [1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1],
        "label": "L1/L2 mixed vs L3 target (public sector)",
    },

    # ── 10. Poulina Group — Industrial Enterprise — L2-L3 mixed, L4 target
    {
        "org": {
            "name": "Poulina Group Holding",
            "industry": "Industrial",
            "industry_other": None,
            "country": "Tunisia",
            "size_band": "Enterprise",
        },
        "targets":       [4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4],
        "domain_levels": [2, 3, 2, 3, 2, 3, 2, 3, 2, 3, 2],
        "label": "L2/L3 mixed vs L4 target (industrial enterprise)",
    },

    # ── 11. Délice Danone — Retail Large — Gap=0 at L3 ───────────────────
    {
        "org": {
            "name": "Délice Holding",
            "industry": "Retail",
            "industry_other": None,
            "country": "Tunisia",
            "size_band": "Large",
        },
        "targets":       [3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3],
        "domain_levels": [3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3],
        "label": "Gap=0 everywhere at L3 (retail large)",
    },

    # ── 12. Tunisair — Other/Aviation Large — L1 everywhere, L3 target ───
    {
        "org": {
            "name": "Tunisair",
            "industry": "Other",
            "industry_other": "Aviation",
            "country": "Tunisia",
            "size_band": "Large",
        },
        "targets":       [3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3],
        "domain_levels": [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
        "label": "L1 everywhere vs L3 target (aviation - Other industry)",
    },

    # ── 13. TOPNET — Telecom SME — Gap=0 at L2 ───────────────────────────
    {
        "org": {
            "name": "TOPNET",
            "industry": "Telecom",
            "industry_other": None,
            "country": "Tunisia",
            "size_band": "SME",
        },
        "targets":       [2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2],
        "domain_levels": [2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2],
        "label": "Gap=0 at L2 (telecom SME)",
    },

    # ── 14. Vermeg — Other/FinTech SME — Near target, L3-L4 mixed ────────
    {
        "org": {
            "name": "Vermeg",
            "industry": "Other",
            "industry_other": "FinTech",
            "country": "Tunisia",
            "size_band": "SME",
        },
        "targets":       [4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4],
        "domain_levels": [3, 4, 3, 4, 3, 4, 3, 4, 3, 4, 3],
        "label": "L3/L4 mixed vs L4 target (fintech SME near target)",
    },

    # ── 15. Telnet Holding — Other/IT Services SME — L2, L4 target ───────
    {
        "org": {
            "name": "Telnet Holding",
            "industry": "Other",
            "industry_other": "IT Services",
            "country": "Tunisia",
            "size_band": "SME",
        },
        "targets":       [4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4],
        "domain_levels": [2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2],
        "label": "L2 everywhere vs L4 target (IT SME high ambition)",
    },

    # ── 16. UIB — Banking Large — L3/L5 mixed vs L4 target ───────────────
    {
        "org": {
            "name": "Union Internationale de Banques",
            "industry": "Banking",
            "industry_other": None,
            "country": "Tunisia",
            "size_band": "Large",
        },
        "targets":       [4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4],
        "domain_levels": [3, 5, 3, 5, 3, 5, 3, 5, 3, 5, 3],
        "label": "L3/L5 mixed vs L4 target (some below, some above)",
    },

    # ── 17. Amen Bank — Banking Large — L4-L5, L3 target (above everywhere)
    {
        "org": {
            "name": "Amen Bank",
            "industry": "Banking",
            "industry_other": None,
            "country": "Tunisia",
            "size_band": "Large",
        },
        "targets":       [3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3],
        "domain_levels": [4, 5, 4, 5, 4, 5, 4, 5, 4, 5, 4],
        "label": "L4/L5 everywhere vs L3 target (exceeds everywhere)",
    },

    # ── 18. CNAM — Healthcare Large — L1 everywhere, L3 target ───────────
    {
        "org": {
            "name": "Caisse Nationale d'Assurance Maladie",
            "industry": "Healthcare",
            "industry_other": None,
            "country": "Tunisia",
            "size_band": "Large",
        },
        "targets":       [3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3],
        "domain_levels": [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
        "label": "L1 everywhere vs L3 target (public healthcare)",
    },

    # ── 19. Richbond — Industrial Large — L3, L2 target (above everywhere)
    {
        "org": {
            "name": "Richbond Tunisie",
            "industry": "Industrial",
            "industry_other": None,
            "country": "Tunisia",
            "size_band": "Large",
        },
        "targets":       [2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2],
        "domain_levels": [3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3],
        "label": "L3 everywhere vs L2 target (manufacturing above target)",
    },

    # ── 20. Carthage Cement — Industrial Large — L2, L3 target ───────────
    {
        "org": {
            "name": "Carthage Cement",
            "industry": "Industrial",
            "industry_other": None,
            "country": "Tunisia",
            "size_band": "Large",
        },
        "targets":       [3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3],
        "domain_levels": [2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2],
        "label": "L2 everywhere vs L3 target (industrial consistent gap 1)",
    },
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def login(session: requests.Session) -> int:
    """Login and return the consultant_id from the session."""
    r = session.post(f"{BASE_URL}/auth/login", json={
        "email":    LOGIN_EMAIL,
        "password": LOGIN_PASSWORD,
    })
    if not r.ok:
        raise RuntimeError(f"Login failed: {r.status_code} {r.text}")
    data = r.json()
    print(f"  ✓ Logged in as {data.get('consultant_name')} (id={data.get('consultant_id')})")
    return data["consultant_id"]


def create_org(session: requests.Session, org_data: dict) -> int:
    r = session.post(f"{BASE_URL}/organizations", json=org_data)
    if not r.ok:
        raise RuntimeError(f"Create org failed: {r.status_code} {r.text}")
    return r.json()["id"]


def create_assessment(session: requests.Session, org_id: int, consultant_id: int) -> int:
    payload = {
        "organization_id": org_id,
        "consultant_id":   consultant_id,
        "engagement_date": ENGAGEMENT_DATE,
    }
    r = session.post(f"{BASE_URL}/assessments", json=payload)
    if not r.ok:
        raise RuntimeError(f"Create assessment failed: {r.status_code} {r.text}")
    return r.json()["id"]


def set_targets(session: requests.Session, assessment_id: int, targets: list):
    """targets is a list of 11 levels, index 0 = domain_id 1."""
    payload = {
        "targets": [
            {"domain_id": i + 1, "target_level": targets[i]}
            for i in range(11)
        ]
    }
    r = session.post(f"{BASE_URL}/assessments/{assessment_id}/targets", json=payload)
    if not r.ok:
        raise RuntimeError(f"Set targets failed: {r.status_code} {r.text}")


def start_assessment(session: requests.Session, assessment_id: int):
    """Move assessment from draft → in_progress so answers can be saved."""
    r = session.post(f"{BASE_URL}/assessments/{assessment_id}/start")
    if not r.ok:
        raise RuntimeError(f"Start assessment failed: {r.status_code} {r.text}")


def fetch_kpi_map(session: requests.Session, assessment_id: int) -> dict:
    """
    Fetch real question IDs and is_inverted flags from the questionnaire API.
    Returns {kpi_id: {"q_ids": [q1, q2, q3, q4], "is_inverted": bool}}.
    """
    r = session.get(f"{BASE_URL}/assessments/{assessment_id}/questionnaire")
    if not r.ok:
        raise RuntimeError(f"Fetch questionnaire failed: {r.status_code} {r.text}")
    domains = r.json()
    kpi_map = {}
    for domain in domains:
        for kpi in domain["kpis"]:
            kpi_id    = kpi["kpi_id"]
            questions = sorted(kpi["questions"], key=lambda q: q["question_number"])
            kpi_map[kpi_id] = {
                "q_ids":       [q["id"] for q in questions],
                "is_inverted": kpi["is_inverted"],
            }
    return kpi_map


def submit_kpi_answers(
    session: requests.Session,
    assessment_id: int,
    kpi_id: int,
    maturity_level: int,
    kpi_map: dict,
):
    payload = build_kpi_answers(kpi_id, maturity_level, kpi_map)
    r = session.post(
        f"{BASE_URL}/assessments/{assessment_id}/answers/kpi/{kpi_id}",
        json=payload,
    )
    if not r.ok:
        raise RuntimeError(f"Answers KPI {kpi_id} failed: {r.status_code} {r.text}")


def submit_assessment(session: requests.Session, assessment_id: int) -> dict:
    r = session.post(f"{BASE_URL}/assessments/{assessment_id}/submit")
    if not r.ok:
        raise RuntimeError(f"Submit failed: {r.status_code} {r.text}")
    return r.json()


# ── Main ──────────────────────────────────────────────────────────────────────

def seed():
    print("=" * 60)
    print("DG Toolkit — Test Assessment Seeder")
    print("=" * 60)

    # Authenticate once; all subsequent requests carry the session cookie
    http = requests.Session()
    consultant_id = login(http)
    results = []

    for i, company in enumerate(COMPANIES, 1):
        name  = company["org"]["name"]
        label = company["label"]
        print(f"\n[{i:02d}/20] {name}")
        print(f"       {label}")

        try:
            # 1. Create org
            org_id = create_org(http, company["org"])
            print(f"       org_id={org_id}")

            # 2. Create assessment
            assessment_id = create_assessment(http, org_id, consultant_id)
            print(f"       assessment_id={assessment_id}")

            # 3. Set per-domain targets
            set_targets(http, assessment_id, company["targets"])
            print(f"       targets set: {company['targets']}")

            # 4. Start assessment (moves draft → in_progress, locks targets)
            start_assessment(http, assessment_id)
            print(f"       assessment started")

            # 5. Fetch real question IDs + inverted flags from the questionnaire
            kpi_map = fetch_kpi_map(http, assessment_id)

            # 6. Submit answers per KPI
            domain_levels = company["domain_levels"]
            for domain_idx, domain_id in enumerate(DOMAIN_IDS):
                level   = domain_levels[domain_idx]
                kpi_ids = KPIS_BY_DOMAIN[domain_id]
                for kpi_id in kpi_ids:
                    submit_kpi_answers(http, assessment_id, kpi_id, level, kpi_map)
            print(f"       all answers submitted")

            # 7. Submit assessment → triggers scoring + layer2 + layer3
            result = submit_assessment(http, assessment_id)
            print(f"       ✓ submitted & scored — overall_level=L{result.get('overall_level', '?')}")

            results.append({
                "company":       name,
                "org_id":        org_id,
                "assessment_id": assessment_id,
                "status":        "ok",
                "label":         label,
            })

            # Small delay to avoid hammering Layer 3 / Ollama concurrently
            time.sleep(2)

        except Exception as e:
            print(f"       ✗ FAILED: {e}")
            results.append({
                "company": name,
                "status":  "failed",
                "error":   str(e),
            })

    # Summary
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

    with open("seed_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\n  Full results saved to seed_results.json")


if __name__ == "__main__":
    seed()

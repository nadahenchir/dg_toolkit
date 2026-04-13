"""
test_embedder_db.py
--------------------
Tests the embedder using real organizations from the DB.
Run from project root: python test_embedder_db.py
"""

from dotenv import load_dotenv
load_dotenv()

import numpy as np
from app.db.connection import get_connection
from app.services.layer2.normalizer import resolve_industry_label
from app.services.layer2.embedder import embed_organization, compute_org_similarity

def fetch_organizations():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name, industry, industry_other, size_band, company_description
                FROM dg_toolkit.organizations
                WHERE deleted_at IS NULL
                AND company_description IS NOT NULL
                ORDER BY id
            """)
            return cur.fetchall()
    finally:
        conn.close()

def main():
    print("Fetching organizations from DB...")
    orgs = fetch_organizations()
    print(f"Found {len(orgs)} organizations\n")

    # build embeddings for all orgs
    org_data = {}
    for (org_id, name, industry, industry_other, size_band, description) in orgs:
        industry_label = resolve_industry_label(industry, industry_other)
        embedding = embed_organization(industry_label, description)
        org_data[org_id] = {
            "name":      name,
            "industry":  industry_label,
            "size_band": size_band,
            "embedding": embedding,
        }

    print(f"Embedded {len(org_data)} organizations\n")

    # pick a few test orgs and show their top matches
    test_ids = [2, 5, 6, 9]  # STB, STAR Insurance, Ooredoo, Clinique

    for test_id in test_ids:
        if test_id not in org_data:
            continue

        current     = org_data[test_id]
        others      = {k: v for k, v in org_data.items() if k != test_id}
        past_keys   = list(others.keys())
        past_vecs   = np.array([others[k]["embedding"] for k in past_keys])

        sims = compute_org_similarity(current["embedding"], past_vecs)

        print("=" * 60)
        print(f"[{test_id}] {current['name']} ({current['industry']}, {current['size_band']}) vs:\n")
        for k, s in sorted(zip(past_keys, sims), key=lambda x: -x[1])[:8]:
            o = org_data[k]
            print(f"  {o['name']:<30} {o['industry']:<15} {o['size_band']:<12} {round(s, 3)}")
        print()

if __name__ == "__main__":
    main()
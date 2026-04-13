import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from app.services.layer2.knn import find_top_k_similar
from app.db.connection import get_connection

# get assessment IDs for STB, STAR Insurance, Ooredoo, Clinique
conn = get_connection()
with conn.cursor() as cur:
    cur.execute("""
        SELECT a.id, o.name, o.industry, o.size_band
        FROM dg_toolkit.assessments a
        JOIN dg_toolkit.organizations o ON o.id = a.organization_id
        WHERE o.id IN (2, 5, 6, 9)
        AND a.deleted_at IS NULL
        ORDER BY o.id
    """)
    test_assessments = cur.fetchall()
conn.close()

for (assessment_id, name, industry, size_band) in test_assessments:
    print("=" * 60)
    print(f"[{assessment_id}] {name} ({industry}, {size_band})")
    
    top_k, sims, confidence = find_top_k_similar(assessment_id)
    
    print(f"Confidence: {confidence}")
    print(f"Top-{len(top_k)} matches:")
    
    # get names for matched assessment IDs
    conn = get_connection()
    with conn.cursor() as cur:
        for pid in top_k:
            cur.execute("""
                SELECT o.name, o.industry, o.size_band
                FROM dg_toolkit.assessments a
                JOIN dg_toolkit.organizations o ON o.id = a.organization_id
                WHERE a.id = %s
            """, (pid,))
            row = cur.fetchone()
            if row:
                print(f"  assessment {pid}: {row[0]} ({row[1]}, {row[2]}) sim={round(sims[pid], 3)}")
    conn.close()
    print()
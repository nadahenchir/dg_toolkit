import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.services.layer2.knn import find_top_k_similar
from app.services.layer2.booster import run_booster
from app.db.connection import get_connection

# Test on assessment 40 (STB)
assessment_id = 40

print("Running KNN...")
top_k, sims, confidence = find_top_k_similar(assessment_id)
print(f"KNN done — confidence={confidence} top_k={top_k}\n")

print("Running booster...")
run_booster(assessment_id, top_k, sims, confidence)
print("Booster done\n")

# verify results
conn = get_connection()
with conn.cursor() as cur:
    cur.execute("""
        SELECT r.kpi_id, k.name, r.priority_score, r.layer2_confidence
        FROM dg_toolkit.recommendations r
        JOIN dg_toolkit.kpis k ON k.id = r.kpi_id
        WHERE r.assessment_id = %s
        ORDER BY r.priority_score DESC
        LIMIT 15
    """, (assessment_id,))
    rows = cur.fetchall()
conn.close()

print("Top 15 recommendations by priority_score:\n")
for (kpi_id, name, score, conf) in rows:
    print(f"  KPI {kpi_id:<3} {name:<45} score={round(float(score),4)}  conf={conf}")
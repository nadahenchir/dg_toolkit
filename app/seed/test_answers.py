import random
from app.db.connection import get_connection, get_cursor

ASSESSMENT_ID = 2  # change if needed

OPTIONS = ['Fully', 'Mostly', 'Partially', 'Slightly', 'Not']

def run():
    conn = get_connection()
    cur  = get_cursor(conn)

    try:
        # Get all KPIs
        cur.execute("SELECT id FROM dg_toolkit.kpis ORDER BY id")
        kpis = [r['id'] for r in cur.fetchall()]

        print(f"Answering {len(kpis)} KPIs for assessment {ASSESSMENT_ID}...")

        for kpi_id in kpis:
            # Get questions for this KPI
            cur.execute("""
                SELECT id, question_number
                FROM dg_toolkit.questions
                WHERE kpi_id = %s
                ORDER BY question_number
            """, [kpi_id])
            questions = cur.fetchall()

            # Pick a random Q1 option (avoid Not/N.A so all questions get answered)
            q1_option = random.choice(['Fully', 'Mostly', 'Partially', 'Slightly'])

            answers = []
            for q in questions:
                if q['question_number'] == 1:
                    answers.append({
                        'question_id':     q['id'],
                        'selected_option': q1_option
                    })
                else:
                    answers.append({
                        'question_id':     q['id'],
                        'selected_option': random.choice(OPTIONS)
                    })

            # Save via direct DB insert (bypassing HTTP for speed)
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)

            OPTION_SCORES = {
                'Fully': 1.00, 'Mostly': 0.75, 'Partially': 0.50,
                'Slightly': 0.25, 'Not': 0.00, 'N.A': None
            }

            for a in answers:
                cur.execute("""
                    INSERT INTO dg_toolkit.answers
                        (assessment_id, question_id, selected_option,
                         is_na, is_hidden, raw_value, answered_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (assessment_id, question_id) DO UPDATE
                        SET selected_option = EXCLUDED.selected_option,
                            is_na           = EXCLUDED.is_na,
                            is_hidden       = EXCLUDED.is_hidden,
                            raw_value       = EXCLUDED.raw_value,
                            updated_at      = EXCLUDED.updated_at
                """, (
                    ASSESSMENT_ID,
                    a['question_id'],
                    a['selected_option'],
                    False,
                    False,
                    OPTION_SCORES[a['selected_option']],
                    now,
                    now,
                ))

            print(f"  KPI {kpi_id}: Q1={q1_option}")

        conn.commit()
        print(f"\nDone — {len(kpis)} KPIs answered")
        print("Now call POST /api/assessments/1/submit in Swagger")

    except Exception as e:
        conn.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    run()
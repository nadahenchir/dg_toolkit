from flask import Blueprint, request, jsonify
import sys
sys.path.insert(0, r'C:\Users\USER\OneDrive\Bureau\dg_toolkit\app\db')
sys.path.insert(0, r'C:\Users\USER\OneDrive\Bureau\dg_toolkit\app')
from connection import get_connection, get_cursor
from datetime import datetime, timezone

answers_bp = Blueprint('answers', __name__)

# Fixed score mapping
OPTION_SCORES = {
    'Fully':     1.00,
    'Mostly':    0.75,
    'Partially': 0.50,
    'Slightly':  0.25,
    'Not':       0.00,
    'N.A':       None,
}

VALID_OPTIONS = set(OPTION_SCORES.keys())


@answers_bp.route('/assessments/<int:assessment_id>/answers', methods=['GET'])
def get_answers(assessment_id):
    conn = get_connection()
    cur  = get_cursor(conn)
    try:
        cur.execute("""
            SELECT a.id, a.question_id, a.selected_option,
                   a.is_na, a.is_hidden, a.raw_value,
                   a.answered_at, a.updated_at,
                   q.kpi_id, q.question_number
            FROM dg_toolkit.answers a
            JOIN dg_toolkit.questions q ON q.id = a.question_id
            WHERE a.assessment_id = %s
            ORDER BY q.kpi_id, q.question_number
        """, [assessment_id])
        rows = cur.fetchall()
        return jsonify([dict(r) for r in rows]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@answers_bp.route('/assessments/<int:assessment_id>/answers/kpi/<int:kpi_id>', methods=['POST'])
def save_kpi_answers(assessment_id, kpi_id):
    """
    Save answers for one KPI in bulk.
    Expects: { "answers": [ {"question_id": 1, "selected_option": "Fully"}, ... ] }
    Gate logic enforced here:
      - Q1 = N.A  → KPI excluded, Q2/Q3/Q4 marked is_hidden = true
      - Q1 = Not  → KPI scores L1, Q2/Q3/Q4 marked is_hidden = true
      - Q1 = else → all questions saved normally
    """
    data = request.get_json()

    if not data.get('answers') or not isinstance(data['answers'], list):
        return jsonify({'error': 'answers must be a non-empty list'}), 400

    conn = get_connection()
    cur  = get_cursor(conn)
    try:
        # Check assessment exists and is in_progress
        cur.execute("""
            SELECT id, status FROM dg_toolkit.assessments
            WHERE id = %s AND deleted_at IS NULL
        """, [assessment_id])
        assessment = cur.fetchone()
        if not assessment:
            return jsonify({'error': 'Assessment not found'}), 404
        if assessment['status'] not in ('in_progress', 'submitted'):
            return jsonify({'error': 'Assessment must be in_progress to save answers'}), 409

        # Get all 4 questions for this KPI ordered by question_number
        cur.execute("""
            SELECT id, question_number, is_gatekeeper
            FROM dg_toolkit.questions
            WHERE kpi_id = %s
            ORDER BY question_number
        """, [kpi_id])
        questions = cur.fetchall()
        if not questions:
            return jsonify({'error': f'KPI {kpi_id} not found'}), 404

        # Build question_id -> question map
        question_map = {q['id']: q for q in questions}
        q_by_number  = {q['question_number']: q for q in questions}

        # Find Q1 answer from submitted data
        answers_by_qid = {a['question_id']: a for a in data['answers']}
        q1 = q_by_number.get(1)
        if not q1:
            return jsonify({'error': 'Could not find Q1 for this KPI'}), 400

        q1_answer = answers_by_qid.get(q1['id'])
        if not q1_answer:
            return jsonify({'error': 'Q1 answer is required'}), 400

        q1_option = q1_answer.get('selected_option')
        if q1_option not in VALID_OPTIONS:
            return jsonify({'error': f'Invalid option: {q1_option}'}), 400

        now = datetime.now(timezone.utc)

        # Determine gate outcome
        q1_is_na      = q1_option == 'N.A'
        q1_is_not     = q1_option == 'Not'
        hide_rest     = q1_is_na or q1_is_not

        # Build final answer rows for all 4 questions
        rows_to_save = []

        for q in questions:
            qid    = q['id']
            q_num  = q['question_number']

            if q_num == 1:
                # Always save Q1 as submitted
                rows_to_save.append({
                    'question_id':     qid,
                    'selected_option': q1_option if q1_option != 'N.A' else None,
                    'is_na':           q1_is_na,
                    'is_hidden':       False,
                    'raw_value':       OPTION_SCORES[q1_option],
                })
            else:
                if hide_rest:
                    # Gate triggered — hide Q2/Q3/Q4 regardless of what was sent
                    rows_to_save.append({
                        'question_id':     qid,
                        'selected_option': None,
                        'is_na':           False,
                        'is_hidden':       True,
                        'raw_value':       None,
                    })
                else:
                    # Normal — save submitted answer
                    submitted = answers_by_qid.get(qid)
                    if not submitted:
                        return jsonify({'error': f'Answer for question {qid} is required'}), 400

                    option = submitted.get('selected_option')
                    if option not in VALID_OPTIONS:
                        return jsonify({'error': f'Invalid option: {option}'}), 400

                    rows_to_save.append({
                        'question_id':     qid,
                        'selected_option': option if option != 'N.A' else None,
                        'is_na':           option == 'N.A',
                        'is_hidden':       False,
                        'raw_value':       OPTION_SCORES[option],
                    })

        # Upsert all rows
        for r in rows_to_save:
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
                assessment_id,
                r['question_id'],
                r['selected_option'],
                r['is_na'],
                r['is_hidden'],
                r['raw_value'],
                now,
                now,
            ))

        conn.commit()
        return jsonify({
            'message': f'Answers saved for KPI {kpi_id}',
            'gate_triggered': hide_rest,
            'q1_is_na': q1_is_na,
            'rows_saved': len(rows_to_save)
        }), 200

    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@answers_bp.route('/assessments/<int:assessment_id>/submit', methods=['POST'])
def submit_assessment(assessment_id):
    """
    Submit assessment after all questions are answered.
    Checks completeness then moves status to submitted.
    """
    conn = get_connection()
    cur  = get_cursor(conn)
    try:
        # Check assessment is in_progress
        cur.execute("""
            SELECT id, status FROM dg_toolkit.assessments
            WHERE id = %s AND deleted_at IS NULL
        """, [assessment_id])
        assessment = cur.fetchone()
        if not assessment:
            return jsonify({'error': 'Assessment not found'}), 404
        if assessment['status'] != 'in_progress':
            return jsonify({'error': f"Assessment is {assessment['status']}, must be in_progress"}), 409

        # Check completeness using DB function
        cur.execute("""
            SELECT dg_toolkit.is_assessment_complete(%s) AS complete
        """, [assessment_id])
        is_complete = cur.fetchone()['complete']
        if not is_complete:
            cur.execute("""
                SELECT q.kpi_id, COUNT(*) AS unanswered
                FROM dg_toolkit.questions q
                LEFT JOIN dg_toolkit.answers a
                    ON a.question_id = q.id
                    AND a.assessment_id = %s
                WHERE (a.id IS NULL OR (a.raw_value IS NULL AND a.is_na = false AND a.is_hidden = false))
                GROUP BY q.kpi_id
                ORDER BY q.kpi_id
            """, [assessment_id])
            incomplete = cur.fetchall()
            return jsonify({
                'error': 'Not all questions are answered',
                'incomplete_kpis': [dict(r) for r in incomplete]
            }), 400
        # Move to submitted
        cur.execute("""
            UPDATE dg_toolkit.assessments
            SET status = 'submitted',
                submitted_at = NOW()
            WHERE id = %s
        """, [assessment_id])
        conn.commit()

    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

    # Run scoring engine — uses its own connection, outside the submit transaction
    from app.services.scoring import run_scoring
    scoring_result = run_scoring(assessment_id)
    return jsonify({
        'message': 'Assessment submitted and scored',
        'assessment_id': assessment_id,
        **scoring_result
    }), 200
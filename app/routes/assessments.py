from flask import Blueprint, request, jsonify
from app.db.connection import get_connection, get_cursor

assessments_bp = Blueprint('assessments', __name__)


@assessments_bp.route('/assessments', methods=['GET'])
def get_assessments():
    limit = request.args.get('limit', type=int)
    conn = get_connection()
    cur  = get_cursor(conn)
    try:
        sql = """
            SELECT a.id, a.status, a.scoring_status, a.layer2_status,
                   a.layer3_status, a.targets_locked, a.engagement_date,
                   a.submitted_at, a.scored_at, a.created_at,
                   o.name AS organization_name,
                   c.full_name AS consultant_name
            FROM dg_toolkit.assessments a
            JOIN dg_toolkit.organizations o ON o.id = a.organization_id
            JOIN dg_toolkit.consultants   c ON c.id = a.consultant_id
            WHERE a.deleted_at IS NULL
            ORDER BY a.created_at DESC
        """
        params = []
        if limit:
            sql += " LIMIT %s"
            params.append(limit)
        cur.execute(sql, params)
        rows = cur.fetchall()
        return jsonify([dict(r) for r in rows]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@assessments_bp.route('/assessments/search', methods=['GET'])
def search_assessments():
    """
    Search assessments by organization name.
    GET /api/assessments/search?q=banque
    Returns up to 8 matching assessments with status info.
    """
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([]), 200

    conn = get_connection()
    cur  = get_cursor(conn)
    try:
        cur.execute("""
            SELECT a.id, a.status, a.scoring_status, a.layer2_status,
                   a.layer3_status, a.created_at,
                   o.name AS organization_name,
                   c.full_name AS consultant_name
            FROM dg_toolkit.assessments a
            JOIN dg_toolkit.organizations o ON o.id = a.organization_id
            JOIN dg_toolkit.consultants   c ON c.id = a.consultant_id
            WHERE a.deleted_at IS NULL
            AND o.name ILIKE %s
            ORDER BY a.created_at DESC
            LIMIT 8
        """, [f'%{q}%'])
        rows = cur.fetchall()
        return jsonify([dict(r) for r in rows]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@assessments_bp.route('/assessments/consultant/<int:consultant_id>', methods=['GET'])
def get_assessments_by_consultant(consultant_id):
    conn = get_connection()
    cur  = get_cursor(conn)
    try:
        cur.execute("""
            SELECT id FROM dg_toolkit.consultants WHERE id = %s
        """, [consultant_id])
        if not cur.fetchone():
            return jsonify({'error': 'Consultant not found'}), 404

        cur.execute("""
            SELECT a.id, a.status, a.scoring_status, a.layer2_status,
                   a.layer3_status, a.targets_locked, a.engagement_date,
                   a.submitted_at, a.scored_at, a.created_at,
                   o.name AS organization_name,
                   c.full_name AS consultant_name
            FROM dg_toolkit.assessments a
            JOIN dg_toolkit.organizations o ON o.id = a.organization_id
            JOIN dg_toolkit.consultants   c ON c.id = a.consultant_id
            WHERE a.consultant_id = %s AND a.deleted_at IS NULL
            ORDER BY a.created_at DESC
        """, [consultant_id])
        rows = cur.fetchall()
        return jsonify([dict(r) for r in rows]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@assessments_bp.route('/assessments/<int:assessment_id>', methods=['GET'])
def get_assessment(assessment_id):
    conn = get_connection()
    cur  = get_cursor(conn)
    try:
        cur.execute("""
            SELECT a.id, a.status, a.scoring_status, a.layer2_status,
                   a.layer3_status, a.targets_locked, a.engagement_date,
                   a.submitted_at, a.scored_at, a.created_at,
                   a.organization_id, a.consultant_id,
                   o.name AS organization_name,
                   c.full_name AS consultant_name
            FROM dg_toolkit.assessments a
            JOIN dg_toolkit.organizations o ON o.id = a.organization_id
            JOIN dg_toolkit.consultants   c ON c.id = a.consultant_id
            WHERE a.id = %s AND a.deleted_at IS NULL
        """, [assessment_id])
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Assessment not found'}), 404
        return jsonify(dict(row)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@assessments_bp.route('/assessments/<int:assessment_id>/questionnaire', methods=['GET'])
def get_questionnaire(assessment_id):
    conn = get_connection()
    cur  = get_cursor(conn)
    try:
        cur.execute("""
            SELECT id, status FROM dg_toolkit.assessments
            WHERE id = %s AND deleted_at IS NULL
        """, [assessment_id])
        assessment = cur.fetchone()
        if not assessment:
            return jsonify({'error': 'Assessment not found'}), 404

        cur.execute("""
            SELECT
                d.id          AS domain_id,
                d.name        AS domain_name,
                d.display_order,
                k.id          AS kpi_id,
                k.name        AS kpi_name,
                k.domain_order AS kpi_order,
                k.is_inverted,
                q.id          AS question_id,
                q.question_number,
                q.question_text,
                q.is_gatekeeper,
                q.allows_na,
                q.opt_fully_text,
                q.opt_mostly_text,
                q.opt_partially_text,
                q.opt_slightly_text,
                q.opt_not_text,
                a.selected_option,
                a.is_na,
                a.is_hidden,
                a.raw_value
            FROM dg_toolkit.domains d
            JOIN dg_toolkit.kpis k      ON k.domain_id = d.id
            JOIN dg_toolkit.questions q ON q.kpi_id    = k.id
            LEFT JOIN dg_toolkit.answers a
                ON a.question_id   = q.id
                AND a.assessment_id = %s
            ORDER BY d.display_order, k.domain_order, q.question_number
        """, [assessment_id])
        rows = cur.fetchall()

        if not rows:
            return jsonify([]), 200

        domains_map = {}
        for r in rows:
            did = r['domain_id']
            kid = r['kpi_id']

            if did not in domains_map:
                domains_map[did] = {
                    'domain_id':     did,
                    'domain_name':   r['domain_name'],
                    'display_order': r['display_order'],
                    'kpis':          {},
                }

            if kid not in domains_map[did]['kpis']:
                domains_map[did]['kpis'][kid] = {
                    'kpi_id':      kid,
                    'kpi_name':    r['kpi_name'],
                    'kpi_order':   r['kpi_order'],
                    'is_inverted': r['is_inverted'],
                    'questions':   [],
                }

            domains_map[did]['kpis'][kid]['questions'].append({
                'id':               r['question_id'],
                'question_number':  r['question_number'],
                'question_text':    r['question_text'],
                'is_gatekeeper':    r['is_gatekeeper'],
                'allows_na':        r['allows_na'],
                'opt_fully_text':   r['opt_fully_text'],
                'opt_mostly_text':  r['opt_mostly_text'],
                'opt_partially_text': r['opt_partially_text'],
                'opt_slightly_text':  r['opt_slightly_text'],
                'opt_not_text':     r['opt_not_text'],
                'selected_option':  r['selected_option'],
                'is_na':            r['is_na'],
                'is_hidden':        r['is_hidden'],
                'raw_value':        float(r['raw_value']) if r['raw_value'] is not None else None,
            })

        result = []
        for d in sorted(domains_map.values(), key=lambda x: x['display_order']):
            kpis_list = sorted(d['kpis'].values(), key=lambda x: x['kpi_order'])
            result.append({
                'domain_id':     d['domain_id'],
                'domain_name':   d['domain_name'],
                'display_order': d['display_order'],
                'kpis':          kpis_list,
            })

        return jsonify(result), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@assessments_bp.route('/assessments', methods=['POST'])
def create_assessment():
    data = request.get_json() or {}

    required = ['organization_id', 'consultant_id']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400

    conn = get_connection()
    cur  = get_cursor(conn)
    try:
        cur.execute("""
            SELECT id FROM dg_toolkit.organizations
            WHERE id = %s AND deleted_at IS NULL
        """, [data['organization_id']])
        if not cur.fetchone():
            return jsonify({'error': 'Organization not found'}), 404

        cur.execute("""
            SELECT id FROM dg_toolkit.consultants
            WHERE id = %s
        """, [data['consultant_id']])
        if not cur.fetchone():
            return jsonify({'error': 'Consultant not found'}), 404

        cur.execute("""
            INSERT INTO dg_toolkit.assessments
                (organization_id, consultant_id, engagement_date)
            VALUES (%s, %s, %s)
            RETURNING id, organization_id, consultant_id, status,
                      scoring_status, layer2_status, layer3_status,
                      targets_locked, engagement_date, created_at
        """, (
            data['organization_id'],
            data['consultant_id'],
            data.get('engagement_date')
        ))
        row = cur.fetchone()
        conn.commit()
        return jsonify(dict(row)), 201
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@assessments_bp.route('/assessments/<int:assessment_id>/targets', methods=['POST'])
def set_targets(assessment_id):
    data = request.get_json() or {}

    if not data.get('targets') or not isinstance(data['targets'], list):
        return jsonify({'error': 'targets must be a non-empty list'}), 400

    conn = get_connection()
    cur  = get_cursor(conn)
    try:
        cur.execute("""
            SELECT id, targets_locked, status
            FROM dg_toolkit.assessments
            WHERE id = %s AND deleted_at IS NULL
        """, [assessment_id])
        assessment = cur.fetchone()
        if not assessment:
            return jsonify({'error': 'Assessment not found'}), 404
        if assessment['targets_locked']:
            return jsonify({'error': 'Targets are locked — assessment is already in progress'}), 409

        for t in data['targets']:
            if 'domain_id' not in t or 'target_level' not in t:
                return jsonify({'error': 'Each target must have domain_id and target_level'}), 400
            if not (1 <= t['target_level'] <= 5):
                return jsonify({'error': 'target_level must be between 1 and 5'}), 400

        for t in data['targets']:
            cur.execute("""
                INSERT INTO dg_toolkit.domain_targets
                    (assessment_id, domain_id, target_level)
                VALUES (%s, %s, %s)
                ON CONFLICT (assessment_id, domain_id) DO UPDATE
                    SET target_level = EXCLUDED.target_level
            """, (assessment_id, t['domain_id'], t['target_level']))

        conn.commit()

        cur.execute("""
            SELECT dt.domain_id, d.name AS domain_name, dt.target_level
            FROM dg_toolkit.domain_targets dt
            JOIN dg_toolkit.domains d ON d.id = dt.domain_id
            WHERE dt.assessment_id = %s
            ORDER BY d.display_order
        """, [assessment_id])
        rows = cur.fetchall()
        return jsonify([dict(r) for r in rows]), 200

    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@assessments_bp.route('/assessments/<int:assessment_id>/start', methods=['POST'])
def start_assessment(assessment_id):
    conn = get_connection()
    cur  = get_cursor(conn)
    try:
        cur.execute("""
            SELECT id, status, targets_locked
            FROM dg_toolkit.assessments
            WHERE id = %s AND deleted_at IS NULL
        """, [assessment_id])
        assessment = cur.fetchone()
        if not assessment:
            return jsonify({'error': 'Assessment not found'}), 404
        if assessment['status'] != 'draft':
            return jsonify({'error': f"Assessment is already {assessment['status']}"}), 409

        cur.execute("""
            SELECT COUNT(*) AS count
            FROM dg_toolkit.domain_targets
            WHERE assessment_id = %s
        """, [assessment_id])
        count = cur.fetchone()['count']
        if count < 11:
            return jsonify({
                'error': f'All 11 domain targets must be set before starting. Currently {count}/11 set.'
            }), 400

        cur.execute("""
            UPDATE dg_toolkit.assessments
            SET status = 'in_progress',
                targets_locked = true
            WHERE id = %s
            RETURNING id, status, targets_locked
        """, [assessment_id])
        row = cur.fetchone()
        conn.commit()
        return jsonify(dict(row)), 200

    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@assessments_bp.route('/assessments/<int:assessment_id>', methods=['DELETE'])
def delete_assessment(assessment_id):
    conn = get_connection()
    cur  = get_cursor(conn)
    try:
        cur.execute("""
            UPDATE dg_toolkit.assessments
            SET deleted_at = NOW()
            WHERE id = %s AND deleted_at IS NULL
            RETURNING id
        """, [assessment_id])
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Assessment not found'}), 404
        conn.commit()
        return jsonify({'message': 'Assessment deleted'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()
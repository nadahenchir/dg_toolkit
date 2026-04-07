from flask import Blueprint, request, jsonify
import sys
sys.path.insert(0, r'C:\Users\USER\OneDrive\Bureau\dg_toolkit\app\db')
from connection import get_connection, get_cursor

assessments_bp = Blueprint('assessments', __name__)


@assessments_bp.route('/assessments', methods=['GET'])
def get_assessments():
    conn = get_connection()
    cur  = get_cursor(conn)
    try:
        cur.execute("""
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
        """)
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


@assessments_bp.route('/assessments', methods=['POST'])
def create_assessment():
    data = request.get_json()

    required = ['organization_id', 'consultant_id']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400

    conn = get_connection()
    cur  = get_cursor(conn)
    try:
        # Verify organization exists and is not deleted
        cur.execute("""
            SELECT id FROM dg_toolkit.organizations
            WHERE id = %s AND deleted_at IS NULL
        """, [data['organization_id']])
        if not cur.fetchone():
            return jsonify({'error': 'Organization not found'}), 404

        # Verify consultant exists
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
    data = request.get_json()

    # Expect: { "targets": [ {"domain_id": 1, "target_level": 3}, ... ] }
    if not data.get('targets') or not isinstance(data['targets'], list):
        return jsonify({'error': 'targets must be a non-empty list'}), 400

    conn = get_connection()
    cur  = get_cursor(conn)
    try:
        # Check assessment exists and targets are not locked
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

        # Validate all targets
        for t in data['targets']:
            if 'domain_id' not in t or 'target_level' not in t:
                return jsonify({'error': 'Each target must have domain_id and target_level'}), 400
            if not (1 <= t['target_level'] <= 5):
                return jsonify({'error': f"target_level must be between 1 and 5"}), 400

        # Upsert all targets
        for t in data['targets']:
            cur.execute("""
                INSERT INTO dg_toolkit.domain_targets
                    (assessment_id, domain_id, target_level)
                VALUES (%s, %s, %s)
                ON CONFLICT (assessment_id, domain_id) DO UPDATE
                    SET target_level = EXCLUDED.target_level
            """, (assessment_id, t['domain_id'], t['target_level']))

        conn.commit()

        # Return all targets for this assessment
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
        # Check assessment exists and is still in draft
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

        # Check all 11 domain targets are set
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

        # Lock targets and move to in_progress
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
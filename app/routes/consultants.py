from flask import Blueprint, request, jsonify
from app.db.connection import get_connection, get_cursor
import re

consultants_bp = Blueprint('consultants', __name__)

_EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')


@consultants_bp.route('/consultants', methods=['GET'])
def get_consultants():
    conn = get_connection()
    cur  = get_cursor(conn)
    try:
        cur.execute("""
            SELECT id, full_name, email, created_at
            FROM dg_toolkit.consultants
            ORDER BY created_at DESC
        """)
        rows = cur.fetchall()
        return jsonify([dict(r) for r in rows]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@consultants_bp.route('/consultants/<int:consultant_id>', methods=['GET'])
def get_consultant(consultant_id):
    conn = get_connection()
    cur  = get_cursor(conn)
    try:
        cur.execute("""
            SELECT id, full_name, email, created_at
            FROM dg_toolkit.consultants
            WHERE id = %s
        """, [consultant_id])
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Consultant not found'}), 404
        return jsonify(dict(row)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@consultants_bp.route('/consultants', methods=['POST'])
def create_consultant():
    data = request.get_json()

    required = ['full_name', 'email']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400

    if not _EMAIL_RE.match(data['email']):
        return jsonify({'error': 'A valid email is required'}), 400

    conn = get_connection()
    cur  = get_cursor(conn)
    try:
        # Upsert — if email already exists, update full_name and return existing row
        cur.execute("""
            INSERT INTO dg_toolkit.consultants (full_name, email)
            VALUES (%s, %s)
            ON CONFLICT (email) DO UPDATE
                SET full_name = EXCLUDED.full_name
            RETURNING id, full_name, email, created_at
        """, (
            data['full_name'],
            data['email'],
        ))
        row = cur.fetchone()
        conn.commit()
        return jsonify(dict(row)), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@consultants_bp.route('/consultants/<int:consultant_id>', methods=['DELETE'])
def delete_consultant(consultant_id):
    conn = get_connection()
    cur  = get_cursor(conn)
    try:
        cur.execute("""
            SELECT id FROM dg_toolkit.consultants
            WHERE id = %s
        """, [consultant_id])
        if not cur.fetchone():
            return jsonify({'error': 'Consultant not found'}), 404

        cur.execute("""
            SELECT COUNT(*) AS count FROM dg_toolkit.assessments
            WHERE consultant_id = %s AND deleted_at IS NULL
        """, [consultant_id])
        if cur.fetchone()['count'] > 0:
            return jsonify({'error': 'Cannot delete consultant — they are linked to existing assessments'}), 409

        cur.execute("""
            DELETE FROM dg_toolkit.consultants
            WHERE id = %s
        """, [consultant_id])
        conn.commit()
        return jsonify({'message': 'Consultant deleted'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

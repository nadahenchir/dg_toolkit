from flask import Blueprint, request, jsonify
import sys
sys.path.insert(0, r'C:\Users\USER\OneDrive\Bureau\dg_toolkit\app\db')
from connection import get_connection, get_cursor

consultants_bp = Blueprint('consultants', __name__)


@consultants_bp.route('/consultants', methods=['GET'])
def get_consultants():
    conn = get_connection()
    cur  = get_cursor(conn)
    try:
        cur.execute("""
            SELECT id, full_name, email, role, created_at
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
            SELECT id, full_name, email, role, created_at
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

    conn = get_connection()
    cur  = get_cursor(conn)
    try:
        cur.execute("""
            INSERT INTO dg_toolkit.consultants (full_name, email, role)
            VALUES (%s, %s, %s)
            RETURNING id, full_name, email, role, created_at
        """, (
            data['full_name'],
            data['email'],
            data.get('role')
        ))
        row = cur.fetchone()
        conn.commit()
        return jsonify(dict(row)), 201
    except Exception as e:
        conn.rollback()
        if 'unique' in str(e).lower():
            return jsonify({'error': 'A consultant with this email already exists'}), 409
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
            DELETE FROM dg_toolkit.consultants
            WHERE id = %s
            RETURNING id
        """, [consultant_id])
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Consultant not found'}), 404
        conn.commit()
        return jsonify({'message': 'Consultant deleted'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()
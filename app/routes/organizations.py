from flask import Blueprint, request, jsonify
import sys
sys.path.insert(0, r'C:\Users\USER\OneDrive\Bureau\dg_toolkit\app\db')
from connection import get_connection, get_cursor

organizations_bp = Blueprint('organizations', __name__)


@organizations_bp.route('/organizations', methods=['GET'])
def get_organizations():
    conn = get_connection()
    cur  = get_cursor(conn)
    try:
        cur.execute("""
            SELECT id, name, industry, country, size_band, notes, created_at
            FROM dg_toolkit.organizations
            WHERE deleted_at IS NULL
            ORDER BY created_at DESC
        """)
        rows = cur.fetchall()
        return jsonify([dict(r) for r in rows]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@organizations_bp.route('/organizations/<int:org_id>', methods=['GET'])
def get_organization(org_id):
    conn = get_connection()
    cur  = get_cursor(conn)
    try:
        cur.execute("""
            SELECT id, name, industry, country, size_band, notes, created_at
            FROM dg_toolkit.organizations
            WHERE id = %s AND deleted_at IS NULL
        """, [org_id])
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Organization not found'}), 404
        return jsonify(dict(row)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@organizations_bp.route('/organizations', methods=['POST'])
def create_organization():
    data = request.get_json()

    required = ['name', 'industry']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400

    valid_industries = [
        'Banking', 'Insurance', 'Telecom', 'Energy',
        'Retail', 'Healthcare', 'Public Sector', 'Other'
    ]
    if data['industry'] not in valid_industries:
        return jsonify({'error': f"industry must be one of: {', '.join(valid_industries)}"}), 400

    conn = get_connection()
    cur  = get_cursor(conn)
    try:
        cur.execute("""
            INSERT INTO dg_toolkit.organizations
                (name, industry, country, size_band, notes)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, name, industry, country, size_band, notes, created_at
        """, (
            data['name'],
            data['industry'],
            data.get('country'),
            data.get('size_band'),
            data.get('notes')
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


@organizations_bp.route('/organizations/<int:org_id>', methods=['DELETE'])
def delete_organization(org_id):
    conn = get_connection()
    cur  = get_cursor(conn)
    try:
        cur.execute("""
            UPDATE dg_toolkit.organizations
            SET deleted_at = NOW()
            WHERE id = %s AND deleted_at IS NULL
            RETURNING id
        """, [org_id])
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Organization not found'}), 404
        conn.commit()
        return jsonify({'message': 'Organization deleted'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()
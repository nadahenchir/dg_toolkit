from flask import Blueprint, request, jsonify, session
from app.db.connection import get_connection, get_cursor
from werkzeug.security import check_password_hash, generate_password_hash
import re

auth_bp = Blueprint('auth', __name__)

_EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')


@auth_bp.route('/auth/register', methods=['POST'])
def register():
    """Bootstrap endpoint — creates the first consultant. Disabled once any consultant exists."""
    conn = get_connection()
    cur  = get_cursor(conn)
    try:
        cur.execute("SELECT COUNT(*) AS count FROM dg_toolkit.consultants")
        if cur.fetchone()['count'] > 0:
            return jsonify({'error': 'Registration is disabled once consultants exist. Contact an admin.'}), 403

        data = request.get_json() or {}
        full_name = (data.get('full_name') or '').strip()
        email     = (data.get('email') or '').strip().lower()
        password  = (data.get('password') or '').strip()

        if not full_name or not email or not password:
            return jsonify({'error': 'full_name, email and password are required'}), 400
        if not _EMAIL_RE.match(email):
            return jsonify({'error': 'A valid email is required'}), 400
        if len(password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400

        password_hash = generate_password_hash(password)
        cur.execute("""
            INSERT INTO dg_toolkit.consultants (full_name, email, password_hash)
            VALUES (%s, %s, %s)
            RETURNING id, full_name, email
        """, (full_name, email, password_hash))
        row = cur.fetchone()
        conn.commit()

        session['consultant_id']    = row['id']
        session['consultant_name']  = row['full_name']
        session['consultant_email'] = row['email']

        return jsonify({
            'message':         'Account created and logged in',
            'consultant_id':   row['id'],
            'consultant_name': row['full_name'],
            'email':           row['email'],
        }), 201

    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@auth_bp.route('/auth/login', methods=['POST'])
def login():
    data = request.get_json() or {}

    email    = (data.get('email') or '').strip().lower()
    password = (data.get('password') or '').strip()

    if not email or not password:
        return jsonify({'error': 'Email and password are required'}), 400

    conn = get_connection()
    cur  = get_cursor(conn)
    try:
        cur.execute("""
            SELECT id, full_name, email, password_hash
            FROM dg_toolkit.consultants
            WHERE email = %s
        """, [email])
        row = cur.fetchone()

        if not row:
            return jsonify({'error': 'Invalid email or password'}), 401

        if not row['password_hash']:
            return jsonify({'error': 'Account has no password set. Contact your administrator.'}), 401

        if not check_password_hash(row['password_hash'], password):
            return jsonify({'error': 'Invalid email or password'}), 401

        # Set session
        session['consultant_id']   = row['id']
        session['consultant_name'] = row['full_name']
        session['consultant_email'] = row['email']

        return jsonify({
            'message':         'Login successful',
            'consultant_id':   row['id'],
            'consultant_name': row['full_name'],
            'email':           row['email'],
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@auth_bp.route('/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Logged out successfully'}), 200


@auth_bp.route('/auth/session', methods=['GET'])
def check_session():
    if 'consultant_id' not in session:
        return jsonify({'authenticated': False}), 401
    return jsonify({
        'authenticated':    True,
        'consultant_id':    session['consultant_id'],
        'consultant_name':  session['consultant_name'],
        'consultant_email': session['consultant_email'],
    }), 200
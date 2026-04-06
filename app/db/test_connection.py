from connection import get_connection, get_cursor

try:
    conn = get_connection()
    cur = get_cursor(conn)
    cur.execute("SELECT current_user, current_database();")
    result = cur.fetchone()
    print(f"Connected successfully!")
    print(f"User: {result['current_user']}")
    print(f"Database: {result['current_database']}")
    conn.close()
except Exception as e:
    print(f"Connection failed: {e}")
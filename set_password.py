from app.db.connection import get_connection, get_cursor
from werkzeug.security import generate_password_hash

conn = get_connection()
cur  = get_cursor(conn)
cur.execute(
    "UPDATE dg_toolkit.consultants SET password_hash = %s WHERE id = 3",
    (generate_password_hash('test123'),)
)
conn.commit()
print('Done')
cur.close()
conn.close()
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import os

load_dotenv()

DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "port":     int(os.getenv("DB_PORT", 5432)),
    "dbname":   os.getenv("DB_NAME", "dg_toolkit"),
    "user":     os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
    "options":  "-c search_path=dg_toolkit,public"
}

def get_connection():
    return psycopg2.connect(**DB_CONFIG)

def get_cursor(conn):
    return conn.cursor(cursor_factory=RealDictCursor)
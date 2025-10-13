# test_db_connect.py
import os
import psycopg2
from urllib.parse import urlparse

url = os.environ.get("DATABASE_URL")
print("DATABASE_URL =", url)

if not url:
    print("Pas de DATABASE_URL définie.")
    raise SystemExit(1)

# adapt if scheme is postgres://
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql://", 1)

print("Using URL:", url)

try:
    parsed = urlparse(url)
    conn = psycopg2.connect(
        dbname=parsed.path.lstrip("/"),
        user=parsed.username,
        password=parsed.password,
        host=parsed.hostname,
        port=parsed.port or 5432,
        sslmode="require"
    )
    cur = conn.cursor()
    cur.execute("SELECT version();")
    print("Connected OK - Postgres version:", cur.fetchone())
    cur.close()
    conn.close()
except Exception as e:
    print("Erreur de connexion :", repr(e))
    raise

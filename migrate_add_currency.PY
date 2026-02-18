import sqlite3
import os

# 🔴 IMPORTANT: this MUST match the DB path your app uses
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv("DB_PATH") or os.path.join(BASE_DIR, "followups.db")
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# Check tables first (debug)
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("Tables:", c.fetchall())

# Add column safely
try:
    c.execute("""
        ALTER TABLE users
        ADD COLUMN  paystack_email_token TEXT DEFAULT 'USD'
    """)
    print("✅ currency column added")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e).lower():
        print("ℹ️ currency column already exists")
    else:
        raise

conn.commit()
conn.close()

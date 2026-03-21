import sqlite3

DB = "followups.db"

conn = sqlite3.connect(DB)
cur = conn.cursor()

cur.execute("UPDATE users SET gmail_token = NULL")
conn.commit()
conn.close()

print("✅ Cleared gmail_token for all users")

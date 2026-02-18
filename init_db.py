import sqlite3

conn = sqlite3.connect("followups.db")
c = conn.cursor()

# USERS
c.execute("""
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT,
    password TEXT,
    is_subscribed INTEGER DEFAULT 0,
    trial_end TEXT
)
""")

# SETTINGS (WITH USER_ID!)
c.execute("""
CREATE TABLE settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    daily_limit INTEGER DEFAULT 20,
    company_name TEXT,
    sender_email TEXT,
    whatsapp_number TEXT
)
""")

# FOLLOWUPS
c.execute("""
CREATE TABLE followups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    client_name TEXT,
    email TEXT,
    phone TEXT,
    followup_type TEXT,
    description TEXT,
    due_date TEXT,
    chase_stage INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending'
)
""")

# SENT LOG
c.execute("""
CREATE TABLE sent_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    followup_id INTEGER,
    sent_at TEXT
)
""")

conn.commit()
print("Fresh DB created with correct schema 🚀")
conn.close()

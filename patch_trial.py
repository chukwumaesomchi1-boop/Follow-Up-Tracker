import sqlite3
from datetime import datetime, timedelta

DB_NAME = "followups.db"

conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()

# Set missing trial_start and trial_end to today + 30 days
now_str = datetime.now().isoformat()
trial_end_str = (datetime.now() + timedelta(days=30)).isoformat()

cursor.execute("""
UPDATE users
SET trial_start = COALESCE(trial_start, ?),
    trial_end = COALESCE(trial_end, ?)
WHERE trial_end IS NULL OR trial_end = ''
""", (now_str, trial_end_str))

conn.commit()
conn.close()

print("Patched users with missing trial_end.")

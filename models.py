from datetime import date, datetime
from database import get_connection


def add_followup(client_name, email, followup_type, description, due_date):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO followups (
            client_name,
            email,
            followup_type,
            description,
            due_date,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        client_name,
        email,
        followup_type,
        description,
        due_date,
        datetime.now().isoformat()
    ))

    conn.commit()
    conn.close()


def mark_followup_done(followup_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE followups
        SET status = 'done'
        WHERE id = ?
    """, (followup_id,))

    conn.commit()
    conn.close()


def get_overdue_followups():
    today = date.today().isoformat()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, client_name, followup_type, due_date
        FROM followups
        WHERE status = 'pending' AND due_date < ?
        ORDER BY due_date ASC
    """, (today,))

    results = cursor.fetchall()
    conn.close()
    return results


def get_due_soon_followups():
    today = date.today().isoformat()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, client_name, followup_type, due_date
        FROM followups
        WHERE status = 'pending' AND due_date >= ?
        ORDER BY due_date ASC
    """, (today,))

    results = cursor.fetchall()
    conn.close()
    return results


def get_done_count():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM followups
        WHERE status = 'done'
    """)

    count = cursor.fetchone()[0]
    conn.close()
    return count


def get_overdue_with_email():
    from datetime import date
    today = date.today().isoformat()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT client_name, email, followup_type, description, due_date
        FROM followups
        WHERE status = 'pending'
        AND due_date < ?
        AND email IS NOT NULL
    """, (today,))

    results = cursor.fetchall()
    conn.close()
    return results

def get_due_for_chase(user_id):
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
    SELECT id, client_name, email, phone,
           followup_type, chase_stage, last_chased
    FROM followups
    WHERE user_id = ?
      AND status = 'pending'
    """, (user_id,))

    rows = c.fetchall()
    conn.close()

    keys = ["id","client_name","email","phone",
            "followup_type","chase_stage","last_chased"]

    return [dict(zip(keys,r)) for r in rows]


def update_chase_stage(fid, stage):
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
      UPDATE followups
      SET chase_stage = ?,
          last_chased = ?
      WHERE id = ?
    """, (stage, datetime.now().isoformat(), fid))

    conn.commit()
    conn.close()

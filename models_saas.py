# models_saas.py
from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime, timedelta, date, timezone
from typing import Any, Optional

from database import get_connection

# IMPORTANT:
# - We use database.get_connection() as the single source of truth.
# - Do NOT re-import or redefine get_connection() anywhere else in this file.

# =========================
# CONSTANTS / HELPERS
# =========================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "followups.db")  # informational only (database.py decides)

_E164_RE = re.compile(r"^\+\d{8,15}$")

# If this shows up in `phone`, you're passing followup_type into phone by mistake.
LIKELY_SWAPPED_VALUES = {"invoice", "proposal", "payment", "meeting", "email", "other"}


def _row_to_dict(cursor: sqlite3.Cursor, row: sqlite3.Row | tuple | None) -> dict | None:
    if row is None:
        return None
    if isinstance(row, sqlite3.Row):
        return dict(row)
    desc = cursor.description
    if not desc:
        return None
    keys = [d[0] for d in desc]
    return dict(zip(keys, row))


def _clean_email(raw: str) -> str:
    return (raw or "").strip().lower()


def _clean_text(raw: str) -> str:
    return (raw or "").strip()


def _utc_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _clean_phone(raw: str) -> str:
    """
    Strict E.164 only: +2348012345678
    - No spaces
    - 8..15 digits after +
    """
    raw0 = raw
    raw = (raw or "").strip()
    if not raw:
        return ""

    if raw.strip().lower() in LIKELY_SWAPPED_VALUES:
        raise ValueError(
            f"Invalid phone number saved: {raw0!r} (looks like followup_type was passed into phone)"
        )

    raw = raw.replace(" ", "")
    if not _E164_RE.fullmatch(raw):
        raise ValueError(f"Invalid phone number saved: {raw0!r}")
    return raw


def _require_channel_fields(preferred_channel: str, email: str, phone: str) -> None:
    ch = (preferred_channel or "whatsapp").strip().lower()

    if ch == "email":
        if not (email or "").strip():
            raise ValueError("Preferred channel is Email but email is missing.")
        return

    if ch in ("sms", "whatsapp"):
        if not (phone or "").strip():
            raise ValueError(f"Preferred channel is {ch.upper()} but phone is missing.")
        return


def resolve_channel(preferred_channel: str, email: str, phone: str) -> str:
    """
    Decide final channel with sane fallbacks.
    """
    ch = (preferred_channel or "whatsapp").strip().lower()
    email_ok = bool((email or "").strip())
    phone_ok = bool((phone or "").strip())

    if ch in ("whatsapp", "sms"):
        if phone_ok:
            return ch
        if email_ok:
            return "email"
        raise ValueError("Missing contact info: add phone or email.")

    if ch == "email":
        if email_ok:
            return "email"
        if phone_ok:
            return "sms"
        raise ValueError("Missing contact info: add phone or email.")

    return "whatsapp" if phone_ok else ("email" if email_ok else "whatsapp")


# =========================
# USER FUNCTIONS
# =========================


from datetime import datetime, timedelta
from typing import Optional
from database import get_connection


def create_user(
    name: str,
    email: str,
    password_hash: str,
    trial_start: Optional[str] = None,
    trial_end: Optional[str] = None,
    trial_days: int = 14,
) -> int:
    conn = get_connection()
    c = conn.cursor()

    now_dt = datetime.utcnow().replace(microsecond=0)
    now = now_dt.isoformat()

    if trial_days > 0:
        if not trial_start:
            trial_start = now

        if not trial_end:
            trial_end = (now_dt + timedelta(days=trial_days)).isoformat()
    else:
        trial_start = None
        trial_end = None

    c.execute(
        """
        INSERT INTO users (
            name,
            email,
            password_hash,
            created_at,
            trial_start,
            trial_end,
            email_verified
        )
        VALUES (?, ?, ?, ?, ?, ?, 0)
        """,
        (
            _clean_text(name),
            _clean_email(email),
            password_hash,
            now,
            trial_start,
            trial_end,
        ),
    )

    conn.commit()
    uid = c.lastrowid
    conn.close()
    return uid






def get_user_by_email(email: str) -> dict | None:
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE lower(email) = ?", (_clean_email(email),))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(uid: int) -> dict | None:
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id=?", (int(uid),))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_users() -> list[dict]:
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT id, email, name, gmail_token, is_subscribed, trial_end
        FROM users
        ORDER BY id ASC
    """)
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_gmail_token(user_id: int, token_json: str | None) -> None:
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET gmail_token=? WHERE id=?", (token_json, int(user_id)))
    conn.commit()
    conn.close()


def get_user_subscription(user_id: int) -> dict:
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT subscription_status, plan, current_period_end,
               stripe_subscription_id, stripe_customer_id
        FROM users
        WHERE id=?
        LIMIT 1
    """, (int(user_id),))
    row = c.fetchone()
    conn.close()

    if not row:
        return {"active": 0, "status": "none", "plan": "", "renews_at": ""}

    status = (row["subscription_status"] or "").strip().lower()
    active = 1 if status in ("active", "trialing") else 0

    return {
        "active": active,
        "status": status,
        "plan": (row["plan"] or ""),
        "renews_at": (row["current_period_end"] or ""),
        "stripe_customer_id": (row["stripe_customer_id"] or ""),
        "stripe_subscription_id": (row["stripe_subscription_id"] or ""),
    }



def deactivate_subscription(user_id: int) -> None:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE users
        SET subscription_status='canceled',
            is_subscribed=0,
            current_period_end=NULL
        WHERE id=?
    """, (int(user_id),))
    conn.commit()
    conn.close()

def mark_payment_failed(user_id: int) -> None:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE users
        SET subscription_status='past_due',
            is_subscribed=0
        WHERE id=?
    """, (int(user_id),))
    conn.commit()
    conn.close()



def set_subscription_active(
    user_id: int,
    stripe_customer_id: str | None = None,
    stripe_subscription_id: str | None = None
) -> None:
    conn = get_connection()
    c = conn.cursor()

    # These columns exist via migration in database.py
    c.execute("""
        UPDATE users
        SET is_subscribed=1,
            trial_end=NULL,
            stripe_customer_id=COALESCE(?, stripe_customer_id),
            stripe_subscription_id=COALESCE(?, stripe_subscription_id),
            subscription_status='active'
        WHERE id=?
    """, (stripe_customer_id, stripe_subscription_id, int(user_id)))

    conn.commit()
    conn.close()

def dict_connection() -> sqlite3.Connection:
    """
    Kept for backwards compatibility.
    This returns Row objects too, and you can do dict(row).
    """
    return _connect()

from database import _connect

def _set_user_subscription_ids(user_id: int, customer_id: str | None, subscription_id: str | None):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE users
        SET stripe_customer_id = COALESCE(stripe_customer_id, ?),
            stripe_subscription_id = COALESCE(stripe_subscription_id, ?)
        WHERE id=?
    """, (customer_id, subscription_id, int(user_id)))
    conn.commit()
    conn.close()

def _find_user_id_by_customer(customer_id: str | None):
    if not customer_id:
        return None
    conn = dict_connection()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE stripe_customer_id=?", (customer_id,))
    row = c.fetchone()
    conn.close()
    return row["id"] if row else None

def _update_subscription_state(user_id: int, active: int, sub_id: str | None, status: str | None):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE users
        SET subscription_active=?,
            stripe_subscription_id=COALESCE(stripe_subscription_id, ?),
            subscription_status=?
        WHERE id=?
    """, (int(active), sub_id, status, int(user_id)))
    conn.commit()
    conn.close()



def activate_subscription(user_id: int) -> None:
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET is_subscribed=1, subscription_status='active' WHERE id=?", (int(user_id),))
    conn.commit()
    conn.close()


def mark_user_subscribed(email: str) -> None:
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET is_subscribed=1, subscription_status='active' WHERE lower(email)=?", (_clean_email(email),))
    conn.commit()
    conn.close()


def mark_user_unsubscribed(email: str) -> None:
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET is_subscribed=0, subscription_status='inactive' WHERE lower(email)=?", (_clean_email(email),))
    conn.commit()
    conn.close()



def mark_user_unsubscribed_by_subscription_id(sub_id: str) -> None:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE users
        SET is_subscribed=0, subscription_status='inactive'
        WHERE stripe_subscription_id=?
    """, (sub_id,))
    conn.commit()
    conn.close()



# def is_trial_active(user: dict | None) -> bool:
#     if not user:
#         return False

#     if int(user.get("is_subscribed") or 0) == 1:
#         return True

#     trial_end = user.get("trial_end")
#     if not trial_end:
#         return False

#     try:
#         end = datetime.fromisoformat(trial_end)
#         return end > datetime.utcnow()
#     except Exception:
#         return False


def is_trial_active(user):
    if not user.get("trial_end"):
        return False
    if user.get("is_subscribed"):
        return False
    return datetime.utcnow() < datetime.fromisoformat(user["trial_end"])


def stats_overview() -> dict[str, int]:
    conn = get_connection()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM users")
    users = int(c.fetchone()[0] or 0)

    c.execute("SELECT COUNT(*) FROM users WHERE is_subscribed=1")
    paid = int(c.fetchone()[0] or 0)

    c.execute("SELECT COUNT(*) FROM followups WHERE status='pending'")
    pending = int(c.fetchone()[0] or 0)

    c.execute("SELECT COUNT(*) FROM followups WHERE status='done'")
    done = int(c.fetchone()[0] or 0)

    conn.close()
    return {"users": users, "paid": paid, "pending": pending, "done": done}


# =========================
# FOLLOW-UP FUNCTIONS
# =========================

def add_followup(
    user_id: int,
    client_name: str,
    email: str,
    followup_type: str,
    description: str,
    due_date: str,
    phone: str = "",
    preferred_channel: str = "email",
    recurring_interval: int = 0,
) -> int:
    email_clean = _clean_email(email)
    phone_clean = _clean_phone(phone) if phone else ""

    # pick channel with fallback logic
    channel = resolve_channel(preferred_channel, email_clean, phone_clean)
    _require_channel_fields(channel, email_clean, phone_clean)

    if not due_date:
        raise ValueError("due_date is required (YYYY-MM-DD)")

    conn = get_connection()
    c = conn.cursor()

    c.execute(
        """
        INSERT INTO followups (
            user_id, client_name, email, phone,
            followup_type, description, due_date,
            created_at, recurring_interval,
            preferred_channel, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        """,
        (
            int(user_id),
            _clean_text(client_name),
            email_clean,
            phone_clean,
            _clean_text(followup_type) or "other",
            _clean_text(description),
            due_date,
            _utc_iso(),
            int(recurring_interval or 0),
            channel,
        ),
    )

    fid = c.lastrowid
    conn.commit()
    conn.close()
    return int(fid)


def promote_draft_to_pending(fid: int, user_id: int) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE followups
        SET status='pending'
        WHERE id=? AND user_id=? AND status='draft'
    """, (int(fid), int(user_id)))
    ok = (c.rowcount or 0) > 0
    conn.commit()
    conn.close()
    return ok


def add_followup_draft(
    user_id: int,
    client_name: str,
    email: str,
    followup_type: str,
    description: str,
    preferred_channel: str = "email",
) -> int:
    """
    Create a draft followup without due_date and without scheduling.
    """
    email_clean = _clean_email(email)
    channel = resolve_channel(preferred_channel, email_clean, "")
    _require_channel_fields(channel, email_clean, "")

    conn = get_connection()
    c = conn.cursor()

    c.execute(
        """
        INSERT INTO followups (
            user_id,
            client_name,
            email,
            phone,
            preferred_channel,
            followup_type,
            description,
            status,
            last_error,
            schedule_enabled,
            next_send_at,
            sent_count,
            last_sent_at,
            due_date,
            created_at,
            recurring_interval,
            scheduled_for
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 0, NULL, 0, NULL, ?, ?, ?, NULL)
        """,
        (
            int(user_id),
            _clean_text(client_name),
            email_clean,
            "",  # phone empty
            channel,
            _clean_text(followup_type) or "other",
            _clean_text(description),
            "draft",
            "",          # due_date empty
            _utc_iso(),  # created_at
            0,           # recurring_interval
        ),
    )

    fid = c.lastrowid
    conn.commit()
    conn.close()
    return int(fid)

# def add_followup_draft(
#     user_id: int,
#     client_name: str,
#     email: str,
#     followup_type: str,
#     description: str,
#     preferred_channel: str = "email",
# ) -> int:
#     """
#     Create a draft followup without due_date and without scheduling.
#     """
#     email_clean = _clean_email(email)
#     channel = resolve_channel(preferred_channel, email_clean, "")
#     _require_channel_fields(channel, email_clean, "")

#     conn = get_connection()
#     c = conn.cursor()

#     c.execute(
#         """
#         INSERT INTO followups (
#             user_id, client_name, email, phone,
#             followup_type, description, due_date,
#             created_at, recurring_interval,
#             preferred_channel, status,
#             schedule_enabled, next_send_at, scheduled_for
#         ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, NULL)
#         """,
#         (
#             int(user_id),
#             _clean_text(client_name),
#             email_clean,
#             "",  # phone empty (email-only)
#             _clean_text(followup_type) or "other",
#             _clean_text(description),
#             "",  # ✅ due_date empty for draft
#             _utc_iso(),
#             0,
#             channel,
#             "draft",
#         ),
#     )

#     fid = c.lastrowid
#     conn.commit()
#     conn.close()
#     return int(fid)



def update_followup(
    fid: int,
    user_id: int,
    client_name: str,
    email: str,
    followup_type: str,
    description: str,
    phone: str = "",
    preferred_channel: str = "email",
) -> bool:
    email_clean = _clean_email(email)
    phone_clean = _clean_phone(phone) if phone else ""

    channel = resolve_channel(preferred_channel, email_clean, phone_clean)
    _require_channel_fields(channel, email_clean, phone_clean)


    conn = get_connection()
    c = conn.cursor()

    c.execute(
        """
        UPDATE followups
        SET client_name=?,
            email=?,
            phone=?,
            followup_type=?,
            description=?,
            preferred_channel=?
        WHERE id=? AND user_id=?
        """,
        (
            _clean_text(client_name),
            email_clean,
            phone_clean,
            _clean_text(followup_type) or "other",
            _clean_text(description),
            channel,
            int(fid),
            int(user_id),
        ),
    )

    ok = (c.rowcount or 0) > 0
    conn.commit()
    conn.close()
    return ok


def get_followup(fid: int, user_id: int) -> dict | None:
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM followups WHERE id=? AND user_id=?", (int(fid), int(user_id)))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def get_followup_by_id(fid: int) -> dict | None:
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM followups WHERE id=?", (int(fid),))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_followup(fid: int, user_id: int) -> bool:
    conn = get_connection()
    c = conn.cursor()

    fid = int(fid)
    user_id = int(user_id)

    # ✅ delete dependent rows first (prevents FK crash)
    c.execute("DELETE FROM whatsapp_logs WHERE followup_id=? AND user_id=?", (fid, user_id))
    c.execute("DELETE FROM activity_logs WHERE followup_id=? AND user_id=?", (fid, user_id))

    # now delete parent
    c.execute("DELETE FROM followups WHERE id=? AND user_id=?", (fid, user_id))
    ok = (c.rowcount or 0) > 0

    conn.commit()
    conn.close()
    return ok


def bulk_mark_done(user_id: int, ids: list[int]) -> int:
    ids = [int(x) for x in ids if str(x).isdigit() or isinstance(x, int)]
    if not ids:
        return 0

    conn = get_connection()
    c = conn.cursor()

    q = ",".join(["?"] * len(ids))
    c.execute(f"""
        UPDATE followups
        SET status='done'
        WHERE user_id=? AND id IN ({q})
    """, [int(user_id)] + ids)

    n = c.rowcount or 0
    conn.commit()
    conn.close()
    return n


def bulk_delete_followups(user_id: int, ids: list[int]) -> int:
    ids = [int(x) for x in ids if str(x).isdigit() or isinstance(x, int)]
    if not ids:
        return 0

    conn = get_connection()
    c = conn.cursor()
    q = ",".join(["?"] * len(ids))

    # ✅ delete children first
    c.execute(f"DELETE FROM whatsapp_logs WHERE user_id=? AND followup_id IN ({q})", [int(user_id)] + ids)
    c.execute(f"DELETE FROM activity_logs WHERE user_id=? AND followup_id IN ({q})", [int(user_id)] + ids)

    c.execute(f"DELETE FROM followups WHERE user_id=? AND id IN ({q})", [int(user_id)] + ids)

    n = c.rowcount or 0
    conn.commit()
    conn.close()
    return n

from pathlib import Path

ALLOWED_EXTS = {"csv"}

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTS

import csv

def read_csv_headers(path: str) -> list[str]:
    # try utf-8-sig first
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            with open(path, "r", newline="", encoding=enc) as f:
                reader = csv.reader(f)
                return next(reader, [])
        except UnicodeDecodeError:
            continue
    raise ValueError("Could not read CSV. Please save/export as UTF-8 CSV and try again.")

def looks_like_text_file(path: str, sample_size: int = 2048) -> bool:
    with open(path, "rb") as f:
        chunk = f.read(sample_size)
    # If it contains lots of null bytes, it’s likely binary (xlsx, etc.)
    return b"\x00" not in chunk

def get_user_followups(user_id: int) -> list[dict]:
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("""
        SELECT
            id,
            client_name,
            followup_type,
            status,
            sent_count,
            last_sent_at,
            COALESCE(substr(next_send_at,1,10), NULLIF(due_date,'')) AS due_date,
            next_send_at,
            schedule_enabled,
            last_error
        FROM followups
        WHERE user_id=?
          AND status IN ('draft','pending','running','passed','failed','sent','scheduled')
        ORDER BY
          CASE WHEN status='draft' THEN 0 ELSE 1 END,
          COALESCE(next_send_at, due_date) ASC
    """, (int(user_id),))

    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_analytics_data() -> dict[str, Any]:
    conn = get_connection()
    c = conn.cursor()

    # ✅ group by the day emails were actually sent
    c.execute("""
        SELECT substr(last_sent_at, 1, 10) AS day, COUNT(*)
        FROM followups
        WHERE last_sent_at IS NOT NULL AND TRIM(last_sent_at) <> ''
        GROUP BY substr(last_sent_at, 1, 10)
        ORDER BY day ASC
    """)
    sent_per_day = c.fetchall()

    c.execute("SELECT COUNT(*) FROM users WHERE is_subscribed=1")
    paid = int(c.fetchone()[0] or 0)

    c.execute("SELECT COUNT(*) FROM users WHERE is_subscribed=0")
    trial = int(c.fetchone()[0] or 0)

    conn.close()
    return {"sent_per_day": sent_per_day, "paid": paid, "trial": trial}



def get_overdue_followups(user_id: int) -> list[dict]:
    today = date.today().isoformat()
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        """
        SELECT id, client_name, followup_type, due_date, status, last_error
        FROM followups
        WHERE user_id=? AND status IN ('pending','failed') AND due_date < ?
        ORDER BY
          CASE WHEN status='failed' THEN 0 ELSE 1 END,
          due_date ASC
        """,
        (int(user_id), today),
    )
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_due_soon_followups(user_id: int) -> list[dict]:
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("""
        SELECT
            id, client_name, followup_type, due_date, status,
            email, phone, preferred_channel,
            last_error, sent_count, last_sent_at,
            scheduled_for, next_send_at, schedule_enabled
        FROM followups
        WHERE user_id=?
          AND status IN ('draft','pending','failed','sent','scheduled','running','passed')
        ORDER BY
          CASE WHEN next_send_at IS NOT NULL THEN 0 ELSE 1 END,
          COALESCE(next_send_at, due_date) ASC,
          id DESC
    """, (int(user_id),))

    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# =========================
# STATUS MARKERS
# =========================

def get_done_count(user_id: int) -> int:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM followups WHERE user_id=? AND status='done'", (int(user_id),))
    n = int(c.fetchone()[0] or 0)
    conn.close()
    return n


def count_done(user_id: int) -> int:
    return get_done_count(user_id)


def mark_followup_done(user_id: int, followup_id: int) -> None:
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE followups SET status='done' WHERE id=? AND user_id=?", (int(followup_id), int(user_id)))
    conn.commit()
    conn.close()


def mark_followup_done_by_email(email: str) -> None:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE followups
        SET status='done'
        WHERE lower(email)=? AND status='pending'
    """, (_clean_email(email),))
    conn.commit()
    conn.close()


def mark_followup_done_by_phone(phone: str) -> None:
    phone_clean = _clean_phone(phone)
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE followups
        SET status='done'
        WHERE phone=? AND status='pending'
    """, (phone_clean,))
    conn.commit()
    conn.close()


def mark_schedule_warning(fid: int, user_id: int, msg: str) -> None:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE followups
        SET last_error=?
        WHERE id=? AND user_id=?
    """, (msg, int(fid), int(user_id)))
    conn.commit()
    conn.close()


def mark_followup_done_by_id(fid: int, user_id: int) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE followups
        SET status='done'
        WHERE id=? AND user_id=?
    """, (int(fid), int(user_id)))
    conn.commit()
    ok = (c.rowcount or 0) > 0
    conn.close()
    return ok


def mark_followup_replied(fid: int, user_id: int) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE followups
        SET status='replied', replied_at=?
        WHERE id=? AND user_id=? AND status IN ('pending','failed','sent')
    """, (_utc_iso(), int(fid), int(user_id)))
    conn.commit()
    ok = (c.rowcount or 0) > 0
    conn.close()
    return ok


# def mark_followup_replied_by_email(user_id: int, email: str) -> int:
#     email_clean = _clean_email(email)
#     if not email_clean:
#         return 0

#     conn = get_connection()
#     c = conn.cursor()
#     c.execute("""
#       UPDATE followups
#       SET status='replied', replied_at=?
#       WHERE user_id=? AND lower(email)=? AND status='sent'
#     """, (_utc_iso(), int(user_id), email_clean))
#     n = c.rowcount
#     conn.commit()
#     conn.close()
#     return n


def mark_send_attempt(fid: int, user_id: int) -> None:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE followups
        SET last_attempt_at=?
        WHERE id=? AND user_id=?
    """, (_utc_iso(), int(fid), int(user_id)))
    conn.commit()
    conn.close()




def mark_followup_failed(fid: int, user_id: int, err: str) -> None:
    mark_send_failed(fid, user_id, err)


def set_status_running(fid: int, user_id: int) -> None:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
      UPDATE followups
      SET status='running'
      WHERE id=? AND user_id=?
    """, (int(fid), int(user_id)))
    conn.commit()
    conn.close()


# =========================
# SCHEDULING (ONE SYSTEM)
# =========================

def set_followup_next_send(fid: int, user_id: int, next_send_at: str | None) -> bool:
    """
    Keep legacy scheduled_for synced with next_send_at
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE followups
        SET next_send_at=?, scheduled_for=?
        WHERE id=? AND user_id=?
    """, (next_send_at, next_send_at, int(fid), int(user_id)))
    conn.commit()
    ok = (c.rowcount or 0) > 0
    conn.close()
    return ok

def clear_followup_schedule(fid: int, user_id: int) -> bool:
    conn = get_connection()
    c = conn.cursor()

    # detect "was ever sent"
    c.execute("""
        SELECT COALESCE(sent_count,0), COALESCE(last_sent_at,'')
        FROM followups
        WHERE id=? AND user_id=?
    """, (int(fid), int(user_id)))
    row = c.fetchone()
    if not row:
        conn.close()
        return False

    sent_count, last_sent_at = row
    was_sent = (int(sent_count or 0) > 0) or bool((last_sent_at or "").strip())

    c.execute("""
      UPDATE followups
      SET schedule_enabled=0,
          schedule_start_date=NULL,
          schedule_end_date=NULL,
          schedule_send_time=NULL,
          schedule_send_time_2=NULL,
          schedule_repeat=NULL,
          schedule_interval=NULL,
          schedule_byweekday=NULL,
          schedule_rel_value=NULL,
          schedule_rel_unit=NULL,
          next_send_at=NULL,
          scheduled_for=NULL,
          -- ✅ only revert status if NOT sent
          status = CASE
            WHEN ? THEN status
            WHEN status IN ('scheduled','passed','failed','running') THEN 'pending'
            ELSE status
          END
      WHERE id=? AND user_id=?
    """, (1 if was_sent else 0, int(fid), int(user_id)))

    conn.commit()
    ok = (c.rowcount or 0) > 0
    conn.close()
    return ok



def mark_schedule_passed(user_id: int, cutoff_iso: str) -> int:
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
        UPDATE followups
        SET status='passed'
        WHERE user_id=?
          AND schedule_enabled=1
          AND next_send_at IS NOT NULL
          AND next_send_at < ?
          AND COALESCE(last_sent_at,'') = ''
          AND status IN ('pending','scheduled')
          AND COALESCE(schedule_repeat,'once') = 'once'
    """, (int(user_id), cutoff_iso))

    n = c.rowcount
    conn.commit()
    conn.close()
    return n

from web.compute_next import compute_next_send_at

def set_followup_schedule_rule(fid: int, user_id: int, rule: dict) -> bool:
    conn = get_connection()
    c = conn.cursor()

    # confirm followup exists
    c.execute("SELECT id FROM followups WHERE id=? AND user_id=?", (int(fid), int(user_id)))
    if not c.fetchone():
        conn.close()
        return False

    # ✅ block scheduling if already sent
    c.execute("""
        SELECT status, COALESCE(sent_count,0) AS sent_count, COALESCE(last_sent_at,'') AS last_sent_at
        FROM followups
        WHERE id=? AND user_id=?
    """, (int(fid), int(user_id)))
    row = c.fetchone()
    if not row:
        conn.close()
        return False

    status, sent_count, last_sent_at = row
    if (status or "").strip().lower() == "sent" or int(sent_count) > 0 or (last_sent_at or "").strip():
        conn.close()
        raise ValueError("This follow-up was already sent. Duplicate it if you want to schedule it again.")

    # --- compute next_send_at instead of trusting rule["next_send_at"] ---
    repeat = (rule.get("schedule_repeat") or "once").strip().lower()
    send_time = (rule.get("schedule_send_time") or "09:00").strip()

    next_send_at = compute_next_send_at(
        start_date=(rule.get("schedule_start_date") or "").strip(),
        send_time=send_time,
        repeat=repeat,
        rel_value=rule.get("schedule_rel_value"),
        rel_unit=rule.get("schedule_rel_unit"),
        input_tz="Africa/Lagos",
        send_time_2=rule.get("schedule_send_time_2"),
        interval=rule.get("schedule_interval"),
        byweekday=rule.get("schedule_byweekday"),
    )

    # normalize blanks -> None (sqlite likes NULLs)
    next_send_at = (next_send_at or "").strip() or None
    start_date = (rule.get("schedule_start_date") or "").strip() or None

    derived_due = start_date or (next_send_at[:10] if next_send_at and len(next_send_at) >= 10 else None)

    c.execute("""
        UPDATE followups
        SET
            schedule_enabled=?,
            schedule_repeat=?,
            schedule_start_date=?,
            schedule_end_date=?,
            schedule_send_time=?,
            schedule_send_time_2=?,
            schedule_interval=?,
            schedule_byweekday=?,
            schedule_rel_value=?,
            schedule_rel_unit=?,
            next_send_at=?,
            scheduled_for=?,
            scheduled_at=?,

            -- ✅ when user schedules, it becomes schedulable again
            status = CASE
                WHEN COALESCE(status,'') IN ('deleted','done','sent') THEN status
                ELSE 'scheduled'
            END,
            last_error = NULL,

            -- ✅ ensure due_date exists (required by schema)
            due_date = COALESCE(NULLIF(TRIM(due_date),''), ?, due_date)

        WHERE id=? AND user_id=?
    """, (
        int(rule.get("schedule_enabled") or 1),
        (rule.get("schedule_repeat") or "once"),
        start_date,
        (rule.get("schedule_end_date") or None),
        send_time,
        (rule.get("schedule_send_time_2") or None),
        int(rule.get("schedule_interval") or 1),
        (rule.get("schedule_byweekday") or None),
        rule.get("schedule_rel_value"),
        rule.get("schedule_rel_unit"),
        next_send_at,                # ✅ computed value
        rule.get("scheduled_for"),
        rule.get("scheduled_at"),
        derived_due,
        int(fid),
        int(user_id),
    ))

    conn.commit()
    conn.close()
    return True




def bulk_set_followup_schedule_rule(user_id: int, ids: list[int], rule: dict) -> int:
    if not ids:
        print("[BULK_SCHED] no ids")
        return 0

    ids = [int(x) for x in ids if str(x).isdigit() or isinstance(x, int)]
    if not ids:
        print("[BULK_SCHED] ids not valid after cleaning")
        return 0

    conn = get_connection()
    c = conn.cursor()

    next_send_at = (rule.get("next_send_at") or "").strip() or None
    start_date = (rule.get("schedule_start_date") or "").strip() or None

    derived_due = None
    if start_date:
        derived_due = start_date
    elif next_send_at and len(next_send_at) >= 10:
        derived_due = next_send_at[:10]

    placeholders = ",".join(["?"] * len(ids))

    # 🔎 DEBUG: see what we're about to touch
    c.execute(f"""
        SELECT id, status, sent_count, last_sent_at
        FROM followups
        WHERE user_id=?
          AND id IN ({placeholders})
    """, [int(user_id), *ids])
    before = [dict(zip([d[0] for d in c.description], r)) for r in c.fetchall()]
    print("[BULK_SCHED][BEFORE]", before)

    params = [
        int(rule.get("schedule_enabled", 1)),
        (rule.get("schedule_repeat") or "once"),
        start_date,
        rule.get("schedule_end_date"),
        (rule.get("schedule_send_time") or "09:00"),
        rule.get("schedule_send_time_2"),
        int(rule.get("schedule_interval") or 1),
        rule.get("schedule_byweekday"),
        rule.get("schedule_rel_value"),
        rule.get("schedule_rel_unit"),
        next_send_at,
        rule.get("scheduled_for"),
        rule.get("scheduled_at"),
        derived_due,        # used only when due_date is empty
        int(user_id),
        *ids,
    ]

    c.execute(f"""
        UPDATE followups
        SET
          schedule_enabled=?,
          schedule_repeat=?,
          schedule_start_date=?,
          schedule_end_date=?,
          schedule_send_time=?,
          schedule_send_time_2=?,
          schedule_interval=?,
          schedule_byweekday=?,
          schedule_rel_value=?,
          schedule_rel_unit=?,
          next_send_at=?,
          scheduled_for=?,
          scheduled_at=?,

          status='scheduled',
          last_error=NULL,

          due_date = COALESCE(NULLIF(TRIM(due_date), ''), ?)

        WHERE user_id=?
          AND id IN ({placeholders})
          AND COALESCE(status,'') NOT IN ('sent','done','deleted')
          AND COALESCE(sent_count,0) = 0
          AND COALESCE(last_sent_at,'') = ''
    """, params)

    n = c.rowcount or 0
    conn.commit()

    # 🔎 DEBUG: confirm what changed
    c.execute(f"""
        SELECT id, status, schedule_enabled, next_send_at, due_date, last_error
        FROM followups
        WHERE user_id=?
          AND id IN ({placeholders})
    """, [int(user_id), *ids])
    after = [dict(zip([d[0] for d in c.description], r)) for r in c.fetchall()]
    print("[BULK_SCHED][AFTER]", after)
    print("[BULK_SCHED] updated rows:", n)

    conn.close()
    return n



def save_gmail_token(user_id: int, token_json: str) -> None:
    """
    Stores Gmail OAuth token (JSON string) for the user.
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE users
        SET gmail_token = ?
        WHERE id = ?
        """,
        (token_json, int(user_id)),
    )

    conn.commit()
    conn.close()


def save_gmail_email(user_id: int, email: str) -> None:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE users
        SET email = COALESCE(email, ?)
        WHERE id = ?
        """,
        (email, int(user_id)),
    )

    conn.commit()
    conn.close()





# =========================
# CHASING / LIMITS
# =========================

def get_due_for_chase(user_id: int, days_overdue_min: int = 0) -> list[dict]:
    conn = get_connection()
    c = conn.cursor()

    today = datetime.utcnow().date().isoformat()
    c.execute(
        """
        SELECT id, user_id, client_name, email, phone, followup_type, description,
               due_date, status, chase_stage, last_chased, recurring_interval, last_generated, preferred_channel
        FROM followups
        WHERE user_id = ?
          AND status = 'pending'
          AND due_date <= ?
        ORDER BY due_date ASC
        """,
        (int(user_id), today),
    )
    rows = c.fetchall()
    conn.close()

    items: list[dict] = []
    now_date = datetime.utcnow().date()

    for r in rows:
        due_date_str = r[7]
        try:
            due_dt = datetime.fromisoformat(due_date_str).date()
        except Exception:
            continue

        overdue_days = (now_date - due_dt).days
        if overdue_days < int(days_overdue_min or 0):
            continue

        items.append(
            {
                "id": r[0],
                "user_id": r[1],
                "client_name": r[2],
                "email": r[3],
                "phone": r[4],
                "followup_type": r[5],
                "description": r[6],
                "due_date": r[7],
                "status": r[8],
                "chase_stage": r[9],
                "last_chased": r[10],
                "recurring_interval": r[11],
                "last_generated": r[12],
                "preferred_channel": r[13],
                "overdue_days": overdue_days,
            }
        )

    return items


def update_chase_stage(fid: int, user_id: int) -> None:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE followups
        SET chase_stage = COALESCE(chase_stage,0) + 1,
            last_chased=?
        WHERE id=? AND user_id=?
    """, (_utc_iso(), int(fid), int(user_id)))
    conn.commit()
    conn.close()


def update_followup_due_date(fid: int, user_id: int, new_date: str) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE followups
        SET due_date = ?
        WHERE id = ? AND user_id = ?
    """, (new_date, int(fid), int(user_id)))
    conn.commit()
    ok = (c.rowcount or 0) > 0
    conn.close()
    return ok


# =========================
# TEMPLATES
# =========================

def save_template(user_id: int, stage: int, content: str) -> None:
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO templates (user_id, stage, content, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, stage)
        DO UPDATE SET content=excluded.content, created_at=excluded.created_at
        """,
        (int(user_id), int(stage), content, _utc_iso()),
    )
    conn.commit()
    conn.close()


def get_templates(user_id: int) -> dict[int, str]:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT stage, content FROM templates WHERE user_id = ?", (int(user_id),))
    rows = c.fetchall()
    conn.close()
    return {int(stage): content for (stage, content) in rows}


# =========================
# SETTINGS
# =========================

def get_daily_limit(user_id: int) -> int:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT daily_limit FROM settings WHERE user_id=?", (int(user_id),))
    row = c.fetchone()
    conn.close()
    return int(row[0]) if row else 20


def set_daily_limit(user_id: int, limit: int) -> None:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO settings(user_id, daily_limit)
        VALUES(?, ?)
        ON CONFLICT(user_id)
        DO UPDATE SET daily_limit=excluded.daily_limit
    """, (int(user_id), int(limit)))
    conn.commit()
    conn.close()


def get_settings(user_id: int) -> dict:
    conn = get_connection()
    c = conn.cursor()

    # ensure column exists
    c.execute("PRAGMA table_info(settings)")
    cols = {row[1] for row in c.fetchall()}
    if "default_country" not in cols:
        c.execute("ALTER TABLE settings ADD COLUMN default_country TEXT DEFAULT 'US'")
        conn.commit()

    c.execute("SELECT daily_limit, default_country FROM settings WHERE user_id=?", (int(user_id),))
    row = c.fetchone()
    conn.close()

    if not row:
        return {"daily_limit": 20, "default_country": "US"}
    return {"daily_limit": int(row[0] or 20), "default_country": (row[1] or "US")}


def set_default_country(user_id: int, country: str) -> None:
    country = (country or "US").strip().upper()
    conn = get_connection()
    c = conn.cursor()

    c.execute("PRAGMA table_info(settings)")
    cols = {row[1] for row in c.fetchall()}
    if "default_country" not in cols:
        c.execute("ALTER TABLE settings ADD COLUMN default_country TEXT DEFAULT 'US'")
        conn.commit()

    c.execute("""
        INSERT INTO settings(user_id, default_country)
        VALUES(?, ?)
        ON CONFLICT(user_id) DO UPDATE SET default_country=excluded.default_country
    """, (int(user_id), country))

    conn.commit()
    conn.close()


def upsert_settings(user_id: int, daily_limit: int, default_country: str) -> None:
    default_country = (default_country or "US").strip().upper()
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO settings(user_id, daily_limit, default_country)
        VALUES(?, ?, ?)
        ON CONFLICT(user_id)
        DO UPDATE SET
            daily_limit=excluded.daily_limit,
            default_country=excluded.default_country
    """, (int(user_id), int(daily_limit), default_country))
    conn.commit()
    conn.close()


# =========================
# SCHEDULER SETTINGS (GLOBAL)
# =========================

def upsert_scheduler_settings(user_id: int, enabled: int, start_date: str, end_date: str, send_time: str, mode: str):
    conn = get_connection()
    c = conn.cursor()

    now = _utc_iso()
    enabled = 1 if str(enabled) in ("1", "true", "True", "on") else 0
    mode = (mode or "both").strip().lower()
    if mode not in ("both", "scheduled_only", "autochase_only"):
        mode = "both"

    send_time = (send_time or "09:00").strip()
    if len(send_time) != 5 or send_time[2] != ":":
        send_time = "09:00"

    c.execute("""
        INSERT INTO scheduler_settings (user_id, enabled, start_date, end_date, send_time, mode, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
          enabled=excluded.enabled,
          start_date=excluded.start_date,
          end_date=excluded.end_date,
          send_time=excluded.send_time,
          mode=excluded.mode,
          updated_at=excluded.updated_at
    """, (int(user_id), int(enabled), start_date, end_date, send_time, mode, now, now))

    conn.commit()
    conn.close()


def get_due_scheduled(user_id: int, now_iso: str):
    """
    Return scheduled items that are due to be sent now.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # DEBUG: dump all followups for this user
    c.execute("""
        SELECT id, status, schedule_enabled, next_send_at
        FROM followups
        WHERE user_id=?
    """, (int(user_id),))
    print("[SCHED][FOLLOWUPS]", [dict(r) for r in c.fetchall()])

    # Actual due scheduled query
    c.execute("""
        SELECT *
        FROM followups
        WHERE user_id=?
          AND schedule_enabled=1
          AND next_send_at IS NOT NULL
          AND next_send_at <= ?
          AND status IN ('pending','scheduled')
        ORDER BY next_send_at ASC
        LIMIT 50
    """, (int(user_id), now_iso))

    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

from web.compute_next import compute_next_send_at

# def mark_send_success(fid: int, user_id: int, now_iso: str, f: dict) -> int:
#     """
#     Marks a followup as successfully sent and updates scheduling state.

#     - If schedule_repeat is "once": disables scheduling and clears next_send_at.
#     - Otherwise: computes next_send_at and keeps schedule_enabled as-is.
#     """
#     conn = get_connection()
#     c = conn.cursor()

#     tick = now_iso

#     repeat = (f.get("schedule_repeat") or "once").strip().lower()

#     if repeat == "once":
#         disable = 1
#         next_at = None
#     else:
#         disable = 0
#         next_at = compute_next_send_at(
#             start_date=f.get("schedule_start_date") or f.get("due_date"),
#             send_time=f.get("schedule_send_time") or "09:00",
#             repeat=repeat,
#             rel_value=f.get("schedule_rel_value"),
#             rel_unit=f.get("schedule_rel_unit"),
#             input_tz="Africa/Lagos",
#         )

#     c.execute("""
#         UPDATE followups
#         SET
#             status='sent',
#             sent_count = COALESCE(sent_count, 0) + 1,
#             last_sent_at = ?,
#             last_attempt_at = ?,
#             last_error = NULL,

#             -- scheduling state
#             schedule_enabled = CASE WHEN ?=1 THEN 0 ELSE schedule_enabled END,
#             next_send_at = CASE WHEN ?=1 THEN NULL ELSE ? END
#         WHERE id=? AND user_id=?
#     """, (tick, tick, disable, disable, next_at, int(fid), int(user_id)))
    
#     n = c.rowcount
#     conn.commit()
#     conn.close()
#     return n

from datetime import datetime
from web.compute_next import compute_next_send_at

from typing import Any
from datetime import datetime
from web.compute_next import compute_next_send_at
from database import get_connection

def mark_send_success(fid: int, user_id: int, f: dict[str, Any] | None = None) -> None:
    f = f or {}

    conn = get_connection()
    c = conn.cursor()
    now_iso = datetime.utcnow().isoformat(timespec="seconds")

    repeat = str(f.get("schedule_repeat") or "once").strip().lower()

    if repeat == "once":
        schedule_enabled = 0
        next_send_at = None
    else:
        schedule_enabled = 1

        # ✅ guarantee a string (never None)
        start_date = (
            str(f.get("schedule_start_date") or "").strip()
            or str((f.get("next_send_at") or "")[:10]).strip()
            or str(f.get("due_date") or "").strip()
        )

        # ultra-safe fallback: today (prevents compute_next_send_at crashing)
        if not start_date:
            start_date = datetime.utcnow().date().isoformat()

        send_time = str(f.get("schedule_send_time") or "09:00").strip()

        next_send_at = compute_next_send_at(
            start_date=start_date,
            send_time=send_time,
            repeat=repeat,
            rel_value=f.get("schedule_rel_value"),
            rel_unit=f.get("schedule_rel_unit"),
            input_tz="Africa/Lagos",
        )

    c.execute(
        """
        UPDATE followups
        SET
            status='sent',
            sent_count = COALESCE(sent_count, 0) + 1,
            last_sent_at = ?,
            last_attempt_at = ?,
            last_error = NULL,
            schedule_enabled = ?,
            next_send_at = ?,
            scheduled_for = ?
        WHERE id=? AND user_id=?
        """,
        (now_iso, now_iso, schedule_enabled, next_send_at, next_send_at, int(fid), int(user_id)),
    )

    conn.commit()
    conn.close()

def mark_send_success_repeating(fid: int, user_id: int) -> None:
    conn = get_connection()
    c = conn.cursor()
    now_iso = datetime.now().isoformat(timespec="seconds")

    c.execute("""
        UPDATE followups
        SET
            sent_count = COALESCE(sent_count, 0) + 1,
            last_sent_at = ?,
            last_attempt_at = ?,
            last_error = NULL,
            status = 'running'
        WHERE id = ? AND user_id = ?
    """, (now_iso, now_iso, int(fid), int(user_id)))

    conn.commit()
    conn.close()



from datetime import datetime

def mark_send_success_once(fid: int, user_id: int) -> None:
    conn = get_connection()
    c = conn.cursor()
    now_iso = datetime.now().isoformat(timespec="seconds")

    c.execute("""
        UPDATE followups
        SET
            status='sent',
            sent_count = COALESCE(sent_count, 0) + 1,
            last_sent_at = ?,
            last_attempt_at = ?,
            last_error = NULL,
            schedule_enabled = 0,
            next_send_at = NULL,
            scheduled_for = NULL
        WHERE id=? AND user_id=?
    """, (now_iso, now_iso, int(fid), int(user_id)))

    conn.commit()
    conn.close()

from datetime import datetime

def mark_send_success_repeat(fid: int, user_id: int, next_send_at: str) -> None:
    conn = get_connection()
    c = conn.cursor()
    now_iso = datetime.now().isoformat(timespec="seconds")

    c.execute("""
        UPDATE followups
        SET
            status='scheduled',
            sent_count = COALESCE(sent_count, 0) + 1,
            last_sent_at = ?,
            last_attempt_at = ?,
            last_error = NULL,
            schedule_enabled = 1,
            next_send_at = ?,
            scheduled_for = ?
        WHERE id=? AND user_id=?
    """, (now_iso, now_iso, next_send_at, next_send_at, int(fid), int(user_id)))

    conn.commit()
    conn.close()


def mark_send_failed(fid: int, user_id: int, reason: str) -> None:
    conn = get_connection()
    c = conn.cursor()
    now_iso = datetime.now().isoformat(timespec="seconds")

    c.execute("""
        UPDATE followups
        SET
            status = 'failed',
            last_error = ?,
            last_attempt_at = ?
        WHERE id = ? AND user_id = ?
    """, (reason, now_iso, int(fid), int(user_id)))

    conn.commit()
    conn.close()






def get_scheduler_settings(user_id: int) -> dict:
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM scheduler_settings WHERE user_id=?", (int(user_id),))
    row = c.fetchone()
    conn.close()

    if not row:
        return {"enabled": 0, "start_date": None, "end_date": None, "send_time": "09:00", "mode": "both"}

    d = dict(row)
    d["enabled"] = int(d.get("enabled") or 0)
    d["send_time"] = d.get("send_time") or "09:00"
    d["mode"] = d.get("mode") or "both"
    return d


def set_last_bulk_run_date(user_id: int, yyyymmdd: str) -> None:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
      UPDATE scheduler_settings
      SET last_bulk_run_date=?, updated_at=?
      WHERE user_id=?
    """, (yyyymmdd, _utc_iso(), int(user_id)))
    conn.commit()
    conn.close()


# =========================
# NOTIFICATIONS
# =========================

def add_notification(user_id: int, message: str) -> None:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO notifications(user_id, message, created_at)
        VALUES (?, ?, ?)
    """, (int(user_id), message, _utc_iso()))
    conn.commit()
    conn.close()


def get_notifications(user_id: int, unread_only: bool = False) -> list[dict]:
    conn = get_connection()
    c = conn.cursor()

    query = """
        SELECT id, message, read, created_at
        FROM notifications
        WHERE user_id=?
    """
    params: list[Any] = [int(user_id)]

    if unread_only:
        query += " AND read=0"
    query += " ORDER BY created_at DESC"

    c.execute(query, params)
    rows = c.fetchall()
    conn.close()

    keys = ["id", "message", "read", "created_at"]
    return [dict(zip(keys, r)) for r in rows]


def mark_notification_read(notification_id: int) -> None:
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE notifications SET read=1 WHERE id=?", (int(notification_id),))
    conn.commit()
    conn.close()


# =========================
# BRANDING
# =========================
def set_branding(
    user_id: int,
    logo_url: str,
    color: str,
    company_name: str = "",
    support_email: str = "",
    footer: str = "",
) -> None:
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
        UPDATE users
        SET
            brand_logo=?,
            brand_color=?,
            company_name=?,
            support_email=?,
            brand_footer=?
        WHERE id=?
    """, (
        _clean_text(logo_url),
        _clean_text(color),
        _clean_text(company_name),
        _clean_email(support_email) if support_email else "",
        _clean_text(footer),
        int(user_id),
    ))

    conn.commit()
    conn.close()


def get_branding(user_id: int | None) -> dict[str, str]:
    if not user_id:
        return {
            "logo": "",
            "color": "#111827",
            "company_name": "",
            "support_email": "",
            "footer": "",
        }

    conn = get_connection()
    c = conn.cursor()

    c.execute("""
        SELECT brand_logo, brand_color, company_name, support_email, brand_footer
        FROM users
        WHERE id=?
    """, (int(user_id),))

    row = c.fetchone()
    conn.close()

    if not row:
        return {
            "logo": "",
            "color": "#111827",
            "company_name": "",
            "support_email": "",
            "footer": "",
        }

    logo, color, company_name, support_email, brand_footer = row

    return {
        "logo": (logo or "").strip(),
        "color": (color or "#111827").strip(),
        "company_name": (company_name or "").strip(),
        "support_email": (support_email or "").strip(),
        "footer": (brand_footer or "").strip(),
    }





# =========================
# EMAIL TEMPLATES
# =========================

def add_email_template(user_id: int, name: str, subject: str, html_content: str) -> None:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO email_templates (user_id, name, subject, html_content, created_at)
        VALUES (?,?,?,?,?)
    """, (int(user_id), _clean_text(name), _clean_text(subject), html_content, _utc_iso()))
    conn.commit()
    conn.close()


def get_email_templates(user_id: int) -> list[dict]:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT id, name, subject, html_content
        FROM email_templates
        WHERE user_id=?
        ORDER BY created_at DESC
    """, (int(user_id),))
    rows = c.fetchall()
    conn.close()

    keys = ["id", "name", "subject", "html_content"]
    return [dict(zip(keys, r)) for r in rows]


def update_email_template(tid: int, name: str, subject: str, html_content: str) -> None:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE email_templates
        SET name=?, subject=?, html_content=?
        WHERE id=?
    """, (_clean_text(name), _clean_text(subject), html_content, int(tid)))
    conn.commit()
    conn.close()


def delete_email_template(tid: int) -> None:
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM email_templates WHERE id=?", (int(tid),))
    conn.commit()
    conn.close()

def get_scheduler_template(user_id: int) -> str:
    """
    Returns the scheduler fallback HTML template for this user.
    Stored in email_templates where name='scheduler'.
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT html_content
        FROM email_templates
        WHERE user_id=? AND lower(name)='scheduler'
        ORDER BY id DESC
        LIMIT 1
    """, (int(user_id),))
    row = c.fetchone()
    conn.close()
    return (row[0] or "").strip() if row else ""


def upsert_scheduler_template(user_id: int, html_content: str) -> None:
    """
    Saves scheduler template as email_templates(name='scheduler').
    If your table doesn’t have UNIQUE(user_id,name), this does update-then-insert.
    """
    html_content = (html_content or "").strip()

    conn = get_connection()
    c = conn.cursor()

    # try update first
    c.execute("""
        UPDATE email_templates
        SET html_content=?
        WHERE user_id=? AND lower(name)='scheduler'
    """, (html_content, int(user_id)))

    if (c.rowcount or 0) == 0:
        c.execute("""
            INSERT INTO email_templates (user_id, name, subject, html_content, created_at)
            VALUES (?, 'scheduler', 'Scheduler Template', ?, ?)
        """, (int(user_id), html_content, _utc_iso()))

    conn.commit()
    conn.close()



def get_scheduler_template(user_id: int) -> str:
    """
    Store scheduler template in email_templates with name='scheduler'.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("""
        SELECT html_content
        FROM email_templates
        WHERE user_id=? AND lower(name)='scheduler'
        ORDER BY id DESC
        LIMIT 1
    """, (int(user_id),))

    row = c.fetchone()
    conn.close()
    return (row["html_content"] or "").strip() if row else ""


def save_scheduler_template(user_id: int, html_content: str) -> None:
    """
    Upsert scheduler template into email_templates (name='scheduler').
    """
    conn = get_connection()
    c = conn.cursor()

    # check if exists
    c.execute("""
        SELECT id
        FROM email_templates
        WHERE user_id=? AND lower(name)='scheduler'
        ORDER BY id DESC
        LIMIT 1
    """, (int(user_id),))
    row = c.fetchone()

    now = datetime.utcnow().replace(microsecond=0).isoformat()
    content = (html_content or "").strip()

    if row:
        tid = int(row[0])
        c.execute("""
            UPDATE email_templates
            SET subject=?, html_content=?, created_at=?
            WHERE id=? AND user_id=?
        """, ("Scheduler Template", content, now, tid, int(user_id)))
    else:
        c.execute("""
            INSERT INTO email_templates (user_id, name, subject, html_content, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (int(user_id), "scheduler", "Scheduler Template", content, now))

    conn.commit()
    conn.close()


# =========================
# WHATSAPP LOGS
# =========================

def log_whatsapp_message(user_id: int, followup_id: int, message: str) -> None:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO whatsapp_logs (user_id, followup_id, message, sent_at)
        VALUES (?, ?, ?, ?)
    """, (int(user_id), int(followup_id), message, _utc_iso()))
    conn.commit()
    conn.close()


def get_whatsapp_logs(user_id: int, followup_id: int | None = None, limit: int = 50) -> list[dict]:
    conn = get_connection()
    c = conn.cursor()

    if followup_id is not None:
        c.execute("""
            SELECT id, user_id, followup_id, message, sent_at
            FROM whatsapp_logs
            WHERE user_id = ? AND followup_id = ?
            ORDER BY id DESC
            LIMIT ?
        """, (int(user_id), int(followup_id), int(limit)))
    else:
        c.execute("""
            SELECT id, user_id, followup_id, message, sent_at
            FROM whatsapp_logs
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
        """, (int(user_id), int(limit)))

    rows = c.fetchall()
    conn.close()

    return [{"id": r[0], "user_id": r[1], "followup_id": r[2], "message": r[3], "sent_at": r[4]} for r in rows]


def count_sent_today(user_id: int) -> int:
    today = datetime.utcnow().date().isoformat()
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT COUNT(*)
        FROM whatsapp_logs
        WHERE user_id = ?
          AND substr(sent_at, 1, 10) = ?
    """, (int(user_id), today))
    n = int(c.fetchone()[0] or 0)
    conn.close()
    return n


# =========================
# MESSAGE OVERRIDE
# =========================

def update_followup_message_override(fid: int, user_id: int, message_override: str | None) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE followups
        SET message_override = ?
        WHERE id = ? AND user_id = ?
    """, (message_override, int(fid), int(user_id)))
    conn.commit()
    ok = (c.rowcount or 0) > 0
    conn.close()
    return ok


# =========================
# RECURRING
# =========================

def generate_recurring_followups() -> None:
    """
    Creates new followups when recurring_interval days have passed since last_generated.
    Uses the *fixed* add_followup() signature.
    """
    conn = get_connection()
    c = conn.cursor()
    today = datetime.utcnow().date()

    c.execute("SELECT * FROM followups WHERE recurring_interval > 0")
    rows = c.fetchall()

    desc = c.description or []
    keys = [d[0] for d in desc]

    for r in rows:
        f = dict(zip(keys, r))

        try:
            if f.get("last_generated"):
                last_gen_date = datetime.fromisoformat(f["last_generated"]).date()
            else:
                last_gen_date = datetime.fromisoformat(f["due_date"]).date()
        except Exception:
            continue

        interval = int(f.get("recurring_interval") or 0)
        if interval <= 0:
            continue

        next_due = last_gen_date + timedelta(days=interval)

        if today >= next_due:
            try:
                add_followup(
                    user_id=int(f["user_id"]),
                    client_name=f.get("client_name") or "",
                    email=f.get("email") or "",
                    phone=f.get("phone") or "",
                    followup_type=f.get("followup_type") or "other",
                    description=f.get("description") or "",
                    due_date=next_due.isoformat(),
                    recurring_interval=interval,
                    preferred_channel=(f.get("preferred_channel") or "email"),
                )
            except Exception:
                # if contact info is broken, skip creating recurring copies
                pass

            c.execute(
                "UPDATE followups SET last_generated=? WHERE id=?",
                (today.isoformat(), int(f["id"])),
            )

    conn.commit()
    conn.close()


# =========================
# ANALYTICS
# =========================

# def get_analytics_data() -> dict[str, Any]:
#     conn = get_connection()
#     c = conn.cursor()

#     c.execute("""
#         SELECT DATE(created_at), COUNT(*)
#         FROM followups
#         WHERE last_sent_at IS NOT NULL AND last_sent_at != ''
#         GROUP BY DATE(created_at)
#         ORDER BY DATE(created_at) ASC
#     """)
#     sent_per_day = c.fetchall()

#     c.execute("SELECT COUNT(*) FROM users WHERE is_subscribed=1")
#     paid = int(c.fetchone()[0] or 0)

#     c.execute("SELECT COUNT(*) FROM users WHERE is_subscribed=0")
#     trial = int(c.fetchone()[0] or 0)

#     conn.close()
#     return {"sent_per_day": sent_per_day, "paid": paid, "trial": trial}


# =========================
# ACTIVITY LOGS
# =========================

def log_action(user_id: int, followup_id: int, action: str, message: str = "") -> None:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO activity_logs (user_id, followup_id, action, message, created_at)
        VALUES (?,?,?,?,?)
    """, (int(user_id), int(followup_id), _clean_text(action), message, _utc_iso()))
    conn.commit()
    conn.close()


# =========================
# SCHEMA HELPERS (OPTIONAL)
# =========================

def ensure_templates_table() -> None:
    """
    Call this once during app startup/migrations (NOT at import time in production).
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            stage INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(user_id, stage)
        );
    """)
    conn.commit()
    conn.close()






# database.py
import os
import sqlite3
from datetime import datetime

# -----------------------------
# DB path (ABSOLUTE by default)
# -----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv("DB_PATH") or os.path.join(BASE_DIR, "followups.db")


# -----------------------------
# Connection helpers
# -----------------------------
def _connect() -> sqlite3.Connection:
    """
    One place to configure SQLite connections.
    - WAL reduces "database is locked" under concurrent reads/writes.
    - foreign_keys ON to enforce relations.
    - busy_timeout to wait rather than instantly failing.
    """
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    # Pragmas
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    conn.execute("PRAGMA busy_timeout = 5000;")  # ms

    return conn


def get_connection():
    return sqlite3.connect(DB_PATH)
print("DB PATH:", os.path.abspath(DB_PATH))

def ensure_auth_columns():
    conn = get_connection()
    c = conn.cursor()

    c.execute("PRAGMA table_info(users)")
    cols = {row[1] for row in c.fetchall()}

    def add_col(sql):
        try:
            c.execute(sql)
        except Exception:
            # column already exists or SQLite being SQLite
            pass

    # --- Auth / Email verification ---
    if "email_verified" not in cols:
        add_col("ALTER TABLE users ADD COLUMN email_verified INTEGER DEFAULT 0")

    if "email_verify_code" not in cols:
        add_col("ALTER TABLE users ADD COLUMN email_verify_code TEXT")

    if "email_verify_expires_at" not in cols:
        add_col("ALTER TABLE users ADD COLUMN email_verify_expires_at TEXT")

    if "email_verify_last_sent_at" not in cols:
        add_col("ALTER TABLE users ADD COLUMN email_verify_last_sent_at TEXT")

    if "email_verified_at" not in cols:
        add_col("ALTER TABLE users ADD COLUMN email_verified_at TEXT")

    # --- Password reset ---
    if "password_reset_code" not in cols:
        add_col("ALTER TABLE users ADD COLUMN password_reset_code TEXT")

    if "password_reset_expires_at" not in cols:
        add_col("ALTER TABLE users ADD COLUMN password_reset_expires_at TEXT")

    conn.commit()
    conn.close()


def ensure_billing_columns():
    """
    Adds Stripe + subscription columns to users (idempotent).

    NOTE: Updated to match the exact SQL you provided:
      - subscription_status TEXT (no DEFAULT in schema-level DDL)
      - stripe_customer_id TEXT
      - stripe_subscription_id TEXT
      - plan TEXT
    (current_period_end is kept as an existing feature.)
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute("PRAGMA table_info(users)")
    cols = {row[1] for row in c.fetchall()}

    def add_col(sql: str):
        try:
            c.execute(sql)
        except Exception:
            pass

    # --- Your requested columns (exact types) ---
    if "subscription_status" not in cols:
        add_col("ALTER TABLE users ADD COLUMN subscription_status TEXT")

    if "stripe_customer_id" not in cols:
        add_col("ALTER TABLE users ADD COLUMN stripe_customer_id TEXT")

    if "stripe_subscription_id" not in cols:
        add_col("ALTER TABLE users ADD COLUMN stripe_subscription_id TEXT")

    if "plan" not in cols:
        add_col("ALTER TABLE users ADD COLUMN plan TEXT")  # monthly|yearly

    # --- Existing feature: keep this column too ---
    if "current_period_end" not in cols:
        add_col("ALTER TABLE users ADD COLUMN current_period_end TEXT")  # ISO string

    conn.commit()
    conn.close()


# def get_connection() -> sqlite3.Connection:
#     """Default connection (Row objects)."""
#     return _connect()


def dict_connection() -> sqlite3.Connection:
    """
    Kept for backwards compatibility.
    This returns Row objects too, and you can do dict(row).
    """
    return _connect()


# -----------------------------
# Migration helpers
# -----------------------------
def _safe_table_name(name: str) -> str:
    """
    Prevent weird injection if someone passes a bad table name.
    Since only your code should call this, it's mainly a guardrail.
    """
    if not name.replace("_", "").isalnum():
        raise ValueError(f"Unsafe table name: {name}")
    return name


def column_exists(cur: sqlite3.Cursor, table: str, column: str) -> bool:
    table = _safe_table_name(table)
    cur.execute(f"PRAGMA table_info({table})")
    rows = cur.fetchall()

    for r in rows:
        # PRAGMA table_info columns: cid, name, type, notnull, dflt_value, pk
        name = r["name"] if isinstance(r, sqlite3.Row) else r[1]
        if name == column:
            return True
    return False


def table_exists(cur: sqlite3.Cursor, table: str) -> bool:
    cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    )
    return cur.fetchone() is not None


def _add_column_if_missing(cur: sqlite3.Cursor, table: str, col: str, col_def: str) -> None:
    # table name is from your code, but keep it safe anyway
    _safe_table_name(table)
    if not column_exists(cur, table, col):
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")


def _ensure_user_branding_columns(conn):
    c = conn.cursor()
    c.execute("PRAGMA table_info(users)")
    cols = {r[1] for r in c.fetchall()}

    def add_col(name, ddl):
        if name not in cols:
            c.execute(ddl)

    add_col("company_name", "ALTER TABLE users ADD COLUMN company_name TEXT")
    add_col("support_email", "ALTER TABLE users ADD COLUMN support_email TEXT")
    add_col("brand_footer", "ALTER TABLE users ADD COLUMN brand_footer TEXT")

    conn.commit()


# -----------------------------
# Init / migrate
# -----------------------------
def init_db() -> None:
    conn = get_connection()
    cur = conn.cursor()

    try:
        # ========= 1) USERS =========
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                gmail_token TEXT,
                created_at TEXT NOT NULL,
                trial_start TEXT,
                trial_end TEXT,
                is_subscribed INTEGER DEFAULT 0,
                brand_logo TEXT DEFAULT '',
                brand_color TEXT DEFAULT '#36A2EB',
                email_verified INTEGER DEFAULT 0,
                auth_provider TEXT,
                google_sub TEXT
            )
            """
        )

        # Ensure branding columns exist (safe on old DBs)
        _ensure_user_branding_columns(conn)

        # Ensure auth/verification columns exist (safe on old DBs)
        ensure_auth_columns()

        # Ensure billing columns exist (safe on old DBs)
        ensure_billing_columns()

        # ========= 2) FOLLOWUPS =========
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS followups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_name TEXT NOT NULL,
                phone TEXT,
                email TEXT,
                followup_type TEXT NOT NULL,
                description TEXT,
                due_date TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                chase_stage INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                last_chased TEXT,
                user_id INTEGER NOT NULL,
                recurring_interval INTEGER DEFAULT 0,
                last_generated TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )

        # ========= 3) WHATSAPP LOGS =========
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS whatsapp_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                followup_id INTEGER,
                user_id INTEGER,
                message TEXT,
                sent_at TEXT,
                FOREIGN KEY(followup_id) REFERENCES followups(id),
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )

        # ========= 4) NOTIFICATIONS =========
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                message TEXT,
                read INTEGER DEFAULT 0,
                created_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )

        # ========= 5) EMAIL TEMPLATES =========
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS email_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name TEXT,
                subject TEXT,
                html_content TEXT,
                created_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )

        # ========= 6) SETTINGS =========
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE,
                daily_limit INTEGER DEFAULT 20,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        # settings upgrades
        _add_column_if_missing(cur, "settings", "default_country", "TEXT DEFAULT 'US'")

        # ========= 6.5) SCHEDULER SETTINGS =========
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS scheduler_settings (
                user_id INTEGER PRIMARY KEY,
                enabled INTEGER DEFAULT 0,
                start_date TEXT,
                end_date TEXT,
                send_time TEXT DEFAULT '09:00',
                mode TEXT DEFAULT 'both',
                last_bulk_run_date TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )

        # Safe incremental migration for older DBs (if table already existed)
        _add_column_if_missing(cur, "scheduler_settings", "enabled", "INTEGER DEFAULT 0")
        _add_column_if_missing(cur, "scheduler_settings", "start_date", "TEXT")
        _add_column_if_missing(cur, "scheduler_settings", "end_date", "TEXT")
        _add_column_if_missing(cur, "scheduler_settings", "send_time", "TEXT DEFAULT '09:00'")
        _add_column_if_missing(cur, "scheduler_settings", "mode", "TEXT DEFAULT 'both'")
        _add_column_if_missing(cur, "scheduler_settings", "last_bulk_run_date", "TEXT")
        _add_column_if_missing(cur, "scheduler_settings", "created_at", "TEXT NOT NULL DEFAULT (datetime('now'))")
        _add_column_if_missing(cur, "scheduler_settings", "updated_at", "TEXT NOT NULL DEFAULT (datetime('now'))")

        # Handle legacy stop_date -> end_date (if stop_date exists)
        if column_exists(cur, "scheduler_settings", "stop_date"):
            cur.execute(
                """
                UPDATE scheduler_settings
                SET end_date = COALESCE(NULLIF(TRIM(end_date), ''), stop_date)
                WHERE stop_date IS NOT NULL AND TRIM(stop_date) <> ''
                """
            )

        # Backfill timestamps if missing/blank (older rows)
        if column_exists(cur, "scheduler_settings", "created_at"):
            cur.execute(
                """
                UPDATE scheduler_settings
                SET created_at = COALESCE(NULLIF(TRIM(created_at), ''), datetime('now'))
                WHERE created_at IS NULL OR TRIM(created_at) = ''
                """
            )
        if column_exists(cur, "scheduler_settings", "updated_at"):
            cur.execute(
                """
                UPDATE scheduler_settings
                SET updated_at = COALESCE(NULLIF(TRIM(updated_at), ''), datetime('now'))
                WHERE updated_at IS NULL OR TRIM(updated_at) = ''
                """
            )

        # ========= 7) CHASE TEMPLATES =========
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                stage INTEGER NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, stage)
            )
            """
        )

        # ========= 8) ACTIVITY LOGS =========
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                followup_id INTEGER,
                action TEXT NOT NULL,
                message TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(followup_id) REFERENCES followups(id)
            )
            """
        )

        # ========= FOLLOWUPS UPGRADES =========
        followups_migrations = [
            ("message_override", "TEXT"),
            ("preferred_channel", "TEXT DEFAULT 'whatsapp'"),
            ("last_error", "TEXT"),
            ("last_attempt_at", "TEXT"),
            ("scheduled_at", "TEXT"),
            ("scheduled_for", "TEXT"),  # ISO datetime string
            ("sent_count", "INTEGER NOT NULL DEFAULT 0"),
            ("last_sent_at", "TEXT"),
            ("replied_at", "TEXT"),
            ("due_at", "TEXT"),
            ("schedule_enabled", "INTEGER NOT NULL DEFAULT 0"),
            ("schedule_repeat", "TEXT DEFAULT 'once'"),  # once|twice_daily|daily|weekly|every_n_days|weekday
            ("schedule_start_date", "TEXT"),
            ("schedule_end_date", "TEXT"),
            ("schedule_send_time", "TEXT DEFAULT '09:00'"),  # 'HH:MM'
            ("schedule_send_time_2", "TEXT"),  # optional for twice/day
            ("schedule_interval", "INTEGER DEFAULT 1"),  # e.g. every 3 days => 3
            ("schedule_byweekday", "TEXT"),  # e.g. 'MO,TU,FR'
            ("schedule_rel_value", "INTEGER"),
            ("schedule_rel_unit", "TEXT"),
            ("next_send_at", "TEXT"),  # ISO datetime
        ]
        for col, col_def in followups_migrations:
            _add_column_if_missing(cur, "followups", col, col_def)

        # ========= USERS UPGRADES =========
        # Keep all existing features, but ensure the 4 requested columns are present
        # with the exact type signature (TEXT without DEFAULT) in this migration list.
        users_migrations = [
            ("subscription_status", "TEXT"),
            ("stripe_customer_id", "TEXT"),
            ("stripe_subscription_id", "TEXT"),
            ("plan", "TEXT"),
            ("current_period_end", "TEXT"),
        ]
        for col, col_def in users_migrations:
            _add_column_if_missing(cur, "users", col, col_def)

        # Optional backfill: prevent NULL subscription_status on old rows
        # (kept as an existing feature/behavior)
        if column_exists(cur, "users", "subscription_status"):
            cur.execute(
                """
                UPDATE users
                SET subscription_status = 'none'
                WHERE subscription_status IS NULL OR TRIM(subscription_status) = ''
                """
            )

        # Helpful indexes (speed + scheduler queries)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_followups_user_status_due ON followups(user_id, status, due_date)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_followups_user_scheduled_for ON followups(user_id, scheduled_for)")
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_followups_user_next_send ON followups(user_id, schedule_enabled, next_send_at)"
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_whatsapp_logs_user_followup ON whatsapp_logs(user_id, followup_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_email_templates_user ON email_templates(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_activity_logs_user ON activity_logs(user_id, created_at)")

        conn.commit()
        print(f"[DB] Initialized + migrated successfully at {DB_PATH}")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ensure_tables() -> None:
    init_db()


# -----------------------------
# Utility reads (optional)
# -----------------------------
def get_followup_by_id(fid: int) -> dict:
    conn = dict_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM followups WHERE id=?", (int(fid),))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else {}


def get_recent_sent_followups(limit: int = 20) -> list[dict]:
    conn = dict_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, email, status, sent_count, last_sent_at, scheduled_for, replied_at
        FROM followups
        WHERE status = 'sent'
        ORDER BY id DESC
        LIMIT ?
        """,
        (int(limit),),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    init_db()

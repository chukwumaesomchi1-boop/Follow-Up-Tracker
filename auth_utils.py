import os
import sqlite3
import secrets
from datetime import datetime, timedelta
from mailer import send_email_smtp
from web.app import build_verify_email_html
#from web.app import _send_verify_code_email
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv("DB_PATH") or os.path.join(BASE_DIR, "followups.db")



def get_connection():
    return sqlite3.connect(DB_PATH)

def _utc_iso():
    return datetime.utcnow().replace(microsecond=0).isoformat()

import os, secrets
from datetime import datetime, timedelta
from database import get_connection
from mailer import send_email_smtp  # whatever your SMTP sender is

def _gen_otp6() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"

def send_verification_code(uid: int, email: str, minutes: int = 15) -> None:
    code = _gen_otp6()
    now = datetime.utcnow().replace(microsecond=0)
    exp = (now + timedelta(minutes=minutes)).isoformat()

    # store in DB
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE users
        SET email_verify_code=?,
            email_verify_expires_at=?,
            email_verify_last_sent_at=?
        WHERE id=?
    """, (code, exp, now.isoformat(), int(uid)))
    conn.commit()
    conn.close()

    app_name = os.getenv("APP_NAME", "Your App")
    subject = f"{app_name} verification code: {code}"
    body_text = f"Your verification code is: {code}\n\nThis code expires in {minutes} minutes."

    # optional html
    body_html = f"""
    <div style="font-family:Arial,sans-serif; font-size:14px; color:#111;">
      <h2 style="margin:0 0 10px;">Verify your email</h2>
      <p>Your verification code is:</p>
      <div style="font-size:28px; font-weight:800; letter-spacing:4px; padding:12px 16px; background:#f3f4f6; display:inline-block; border-radius:10px;">
        {code}
      </div>
      <p style="margin-top:14px; color:#555;">Expires in {minutes} minutes.</p>
    </div>
    """.strip()

    send_email_smtp(
        to_email=email,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
    )

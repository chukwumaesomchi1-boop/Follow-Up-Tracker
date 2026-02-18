import csv
import re
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

# IMPORTANT: For the SaaS/web app, import from models_saas (not models)
from models_saas import add_followup


HEADER_ALIASES = {
    "client_name": {"client_name", "name", "client", "customer"},
    "email": {"email", "email_address", "e_mail", "e-mail", "email_before"},
    "phone": {"phone", "phone_number", "mobile", "cell", },
    "followup_type": {"followup_type", "type", "follow_up_type", "follow-up_type"},
    "description": {"description", "note", "notes", "details"},
    "due_date": {"due_date", "date", "followup_date", "follow_up_date", "due"},
}

PREFERRED = {
    "client_name": ["client_name", "customer", "client", "name"],
    "email": ["email", "email_address", "e_mail", "e-mail", "email_before"],
    "phone": ["phone", "phone_number", "mobile", "cell", "phone_before"],
    "followup_type": ["followup_type", "follow_up_type", "follow-up_type", "type"],
    "description": ["description", "details", "notes", "note"],
    "due_date": ["due_date", "followup_date", "follow_up_date", "due", "date"],
}



def normalize_header(h: str) -> str:
    # "Client Name" -> "client_name", "E-mail" -> "e_mail"
    h = (h or "").strip().lower()
    h = re.sub(r"[^a-z0-9]+", "_", h)
    h = re.sub(r"_+", "_", h).strip("_")
    return h


def build_header_map(fieldnames) -> Dict[str, str]:
    """
    Returns: canonical -> actual CSV column name
    """
    normalized_cols = {normalize_header(col): col for col in fieldnames}

    # Only allow matches that are in our alias sets (safety)
    allowed = {}
    for canonical, aliases in HEADER_ALIASES.items():
        for a in aliases:
            if a in normalized_cols:
                allowed.setdefault(canonical, set()).add(a)

    # Choose best match using PREFERRED order
    result = {}
    for canonical, prefs in PREFERRED.items():
        for pref in prefs:
            if pref in allowed.get(canonical, set()):
                result[canonical] = normalized_cols[pref]
                break

    return result





# import_csv.py
import csv
from datetime import datetime
from models_saas import add_followup

import hashlib
from database import get_connection

def _import_key(user_id: int, email: str, due_date: str, description: str, followup_type: str) -> str:
    raw = f"{user_id}|{(email or '').strip().lower()}|{(due_date or '').strip()}|{(followup_type or '').strip().lower()}|{(description or '').strip()}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()

def _import_seen(conn, user_id: int, key: str) -> bool:
    # uses activity_logs as a cheap dedupe store if you already have it
    # BUT better is to store key on followups table (see option 2).
    cur = conn.cursor()
    cur.execute("""
        SELECT 1
        FROM activity_logs
        WHERE user_id=? AND action='import_csv' AND message=?
        LIMIT 1
    """, (int(user_id), key))
    return cur.fetchone() is not None

def _import_mark(conn, user_id: int, followup_id: int, key: str) -> None:
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO activity_logs(user_id, followup_id, action, message, created_at)
        VALUES(?, ?, 'import_csv', ?, ?)
    """, (int(user_id), int(followup_id), key, datetime.utcnow().replace(microsecond=0).isoformat()))


# def import_followups_from_csv(file_path: str, user_id: int, mapping: dict | None = None) -> dict:
#     mapping = mapping or {}

#     col_name = (mapping.get("client_name") or "").strip()
#     col_email = (mapping.get("email") or "").strip()
#     col_desc = (mapping.get("description") or "").strip()
#     col_due = (mapping.get("due_date") or "").strip()
#     preferred_channel = (mapping.get("preferred_channel") or "email").strip().lower() or "email"

#     imported = 0
#     skipped = 0
#     errors: list[str] = []

#     encodings = ("utf-8-sig", "utf-8", "cp1252", "latin-1")
#     last_exc = None

#     for enc in encodings:
#         try:
#             with open(file_path, "r", newline="", encoding=enc) as f:
#                 reader = csv.DictReader(f)
#                 headers = reader.fieldnames or []

#                 if col_name and col_name not in headers:
#                     return {"imported": 0, "skipped": 0, "errors": [f"Mapped Client Name column '{col_name}' not found in CSV headers."]}
#                 if col_email and col_email not in headers:
#                     return {"imported": 0, "skipped": 0, "errors": [f"Mapped Email column '{col_email}' not found in CSV headers."]}

#                 # ✅ single connection for whole import (fast + enables dedupe markers)
#                 conn = get_connection()
#                 try:
#                     for i, row in enumerate(reader, start=2):
#                         try:
#                             client_name = (row.get(col_name) or "").strip() if col_name else ""
#                             email = (row.get(col_email) or "").strip() if col_email else ""
#                             description = (row.get(col_desc) or "").strip() if col_desc else ""

#                             due_date_raw = (row.get(col_due) or "").strip() if col_due else ""
#                             if due_date_raw:
#                                 try:
#                                     due_date = datetime.strptime(due_date_raw[:10], "%Y-%m-%d").date().isoformat()
#                                 except Exception:
#                                     raise ValueError(f"Invalid due date '{due_date_raw}' (expected YYYY-MM-DD)")
#                             else:
#                                 due_date = datetime.utcnow().date().isoformat()

#                             if not email:
#                                 skipped += 1
#                                 continue

#                             followup_type = "other"

#                             # ✅ dedupe key
#                             key = _import_key(user_id, email, due_date, description, followup_type)
#                             if _import_seen(conn, user_id, key):
#                                 skipped += 1
#                                 continue

#                             # ⚠️ phone format: your add_followup enforces strict E.164.
#                             # If CSV phones are messy, either clean them or just drop phone on import.
#                             # safest: keep phone only if it starts with "+"
                            
#                             fid = add_followup(
#                                 user_id=int(user_id),
#                                 client_name=client_name or "(No name)",
#                                 email=email,
#                                 followup_type=followup_type,
#                                 description=description,
#                                 due_date=due_date,
#                                 preferred_channel=preferred_channel,
#                                 recurring_interval=0,
#                             )

#                             # ✅ mark dedupe record so repeat posts won’t duplicate
#                             _import_mark(conn, user_id, fid, key)

#                             imported += 1

#                         except Exception as e:
#                             skipped += 1
#                             errors.append(f"Row {i}: {e}")

#                     conn.commit()
#                 finally:
#                     conn.close()

#             return {"imported": imported, "skipped": skipped, "errors": errors}

#         except UnicodeDecodeError as e:
#             last_exc = e
#             continue

#     return {"imported": 0, "skipped": 0, "errors": [f"Could not read CSV file (encoding issue). Try exporting as UTF-8 CSV. Details: {last_exc}"]}


import csv
import re
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

from models_saas import add_followup

E164_RE = re.compile(r"^\+\d{8,15}$")

CANON_FIELDS = ["client_name", "email", "phone", "followup_type", "description", "due_date"]

def parse_date_flexible(date_str: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    s = (date_str or "").strip()
    if not s:
        return None, "Missing due_date."

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date().isoformat(), None
        except ValueError:
            pass

    return None, "Invalid due_date. Use YYYY-MM-DD or DD/MM/YYYY."


def normalize_phone_with_default(phone_raw: str, default_country: str) -> Tuple[str, Optional[str]]:
    p = (phone_raw or "").strip()
    if not p:
        return "", None

    default_country = (default_country or "US").strip().upper()

    # no guessing: only allow NG leading-0 conversion
    if default_country == "NG" and re.fullmatch(r"0\d{10}", p):
        p = "+234" + p[1:]

    # strip spaces/dashes only (still “hard rules”)
    p = p.replace(" ", "").replace("-", "")

    if not E164_RE.fullmatch(p):
        return "", f"Invalid phone '{phone_raw}'. Use E.164 like +2348012345678."
    return p, None


import csv
from datetime import datetime

def import_followups_from_csv(
    file_path: str,
    user_id: int,
    mapping: dict | None = None,
    progress_cb=None,
) -> dict:
    mapping = mapping or {}

    col_name = (mapping.get("client_name") or "").strip()
    col_email = (mapping.get("email") or "").strip()
    col_phone = (mapping.get("phone") or "").strip()
    col_desc = (mapping.get("description") or "").strip()
    col_due = (mapping.get("due_date") or "").strip()
    preferred_channel = (mapping.get("preferred_channel") or "email").strip().lower() or "email"

    imported = 0
    skipped = 0
    errors: list[str] = []

    encodings = ("utf-8-sig", "utf-8", "cp1252", "latin-1")
    last_exc = None

    for enc in encodings:
        try:
            # 1) count rows (for progress %)
            with open(file_path, "r", newline="", encoding=enc) as f:
                total = max(sum(1 for _ in f) - 1, 0)  # minus header

            done = 0
            if progress_cb:
                progress_cb(done, total)

            # 2) actual import
            with open(file_path, "r", newline="", encoding=enc) as f:
                reader = csv.DictReader(f)
                headers = reader.fieldnames or []

                if col_name and col_name not in headers:
                    return {"imported": 0, "skipped": 0, "errors": [f"Mapped Client Name column '{col_name}' not found in CSV headers."]}
                if col_email and col_email not in headers:
                    return {"imported": 0, "skipped": 0, "errors": [f"Mapped Email column '{col_email}' not found in CSV headers."]}

                for i, row in enumerate(reader, start=2):
                    try:
                        client_name = (row.get(col_name) or "").strip() if col_name else ""
                        email = (row.get(col_email) or "").strip() if col_email else ""
                        phone = (row.get(col_phone) or "").strip() if col_phone else ""
                        description = (row.get(col_desc) or "").strip() if col_desc else ""

                        due_date_raw = (row.get(col_due) or "").strip() if col_due else ""
                        if due_date_raw:
                            try:
                                due_date = datetime.strptime(due_date_raw[:10], "%Y-%m-%d").date().isoformat()
                            except Exception:
                                raise ValueError(f"Invalid due date '{due_date_raw}' (expected YYYY-MM-DD)")
                        else:
                            due_date = datetime.utcnow().date().isoformat()

                        if not email:
                            skipped += 1
                            done += 1
                            if progress_cb and (done % 5 == 0 or done == total):
                                progress_cb(done, total)
                            continue

                        add_followup(
                            user_id=int(user_id),
                            client_name=client_name or "(No name)",
                            email=email,
                            phone=phone,
                            followup_type="other",
                            description=description,
                            due_date=due_date,
                            preferred_channel=preferred_channel,
                            recurring_interval=0,
                        )

                        imported += 1
                        done += 1

                        if progress_cb and (done % 5 == 0 or done == total):
                            progress_cb(done, total)

                    except Exception as e:
                        skipped += 1
                        done += 1
                        errors.append(f"Row {i}: {e}")
                        if progress_cb and (done % 5 == 0 or done == total):
                            progress_cb(done, total)

            if progress_cb:
                progress_cb(total, total)

            return {"imported": imported, "skipped": skipped, "errors": errors}

        except UnicodeDecodeError as e:
            last_exc = e
            continue

    return {"imported": 0, "skipped": 0, "errors": [f"Could not read CSV file (encoding issue). Try exporting as UTF-8 CSV. Details: {last_exc}"]}

# chase.py
from __future__ import annotations

import sqlite3
from typing import Any, Mapping, Optional

from database import get_connection

# -----------------------------
# Scheduler-only template (single)
# -----------------------------

DEFAULT_SCHEDULER_TEMPLATE = """
Hi {name},

Just a quick follow-up about {type}.

{description}

— Sent via Followups
""".strip()


def load_scheduler_template_from_db(user_id: int) -> str | None:
    """
    Loads ONE scheduler template from email_templates table.

    Priority:
      1) name='scheduler'
      2) name='default'
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute(
        """
        SELECT name, html_content
        FROM email_templates
        WHERE user_id=?
          AND lower(trim(name)) IN ('scheduler','default')
        """,
        (int(user_id),),
    )
    rows = c.fetchall()
    conn.close()

    # prefer scheduler over default
    best = None
    for r in rows:
        nm = (r["name"] or "").strip().lower()
        content = (r["html_content"] or "").strip()
        if not content:
            continue
        if nm == "scheduler":
            return content
        if nm == "default":
            best = content

    return best


def _safe_format(template: str, data: Mapping[str, Any]) -> str:
    class SafeDict(dict):
        def __missing__(self, key):
            return "{" + key + "}"

    try:
        return template.format_map(SafeDict(**data))
    except Exception:
        return str(template)


def render_email_html(subject: str, body_text_or_html: str) -> str:
    """
    Wrap message into a nice email HTML shell.
    - If the body already looks like HTML, we still wrap it.
    """
    body = (body_text_or_html or "").strip()

    # super light "is html?" check
    looks_html = "<" in body and ">" in body

    if not looks_html:
        # convert plain text to HTML safely-ish
        # (minimal: preserve line breaks)
        body = (
            body.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\n", "<br>")
        )

    subject_esc = (
        (subject or "")
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )

    return f"""
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{subject_esc}</title>
  </head>
  <body style="margin:0;padding:0;background:#f6f7fb;font-family:Arial,sans-serif;">
    <div style="max-width:640px;margin:0 auto;padding:18px;">
      <div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:16px;overflow:hidden;">
        <div style="padding:16px 18px;border-bottom:1px solid #f1f5f9;background:#fbfdff;">
          <div style="font-size:12px;color:#64748b;">Follow-up</div>
          <div style="font-size:18px;font-weight:800;color:#0f172a;margin-top:4px;">
            {subject_esc}
          </div>
        </div>
        <div style="padding:18px;color:#0f172a;line-height:1.6;font-size:14px;">
          {body}
        </div>
      </div>
      <div style="text-align:center;color:#94a3b8;font-size:12px;margin-top:12px;">
        Sent by your scheduler
      </div>
    </div>
  </body>
</html>
""".strip()


def build_message_preview(f: Mapping[str, Any], user_id: Optional[int] = None) -> str:
    """
    Scheduler-safe message builder (NO stages).

    PRECEDENCE:
      1) message_override (wins)
      2) description (wins)
      3) scheduler template (one template)
    Returns HTML (wrapped).
    """
    override = (f.get("message_override") or "").strip()
    desc = (f.get("description") or "").strip()

    name = (f.get("client_name") or "").strip() or "there"
    ftype = (f.get("followup_type") or "follow-up").strip()

    # Subject used by scheduler
    subject = f"Follow-up: {ftype}"

    # 1) override
    if override:
        return render_email_html(subject, override)

    # 2) description
    if desc:
        return render_email_html(subject, desc)

    # 3) single scheduler template
    uid = user_id if user_id is not None else f.get("user_id")
    try:
        uid_int = int(uid) if uid is not None else 0
    except Exception:
        uid_int = 0

    tpl = None
    if uid_int > 0:
        try:
            tpl = load_scheduler_template_from_db(uid_int)
        except Exception:
            tpl = None

    template = (tpl or DEFAULT_SCHEDULER_TEMPLATE)

    body = _safe_format(
        template,
        {
            "name": name,
            "type": ftype,
            "description": "",  # no description available in this fallback
        },
    )

    return render_email_html(subject, body)

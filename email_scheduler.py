# email_outgoing.py

import re
import html as _html
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from googleapiclient.discovery import build

from models_saas import get_scheduler_template, get_branding
from scheduler_render import render_scheduler_html
from email_renderer import render_followup_email_html, plain_to_html
from gmail_sync import _creds_from_user, _save_refreshed_token


# ----------------------------
# Helpers
# ----------------------------
_HTML_TAG_RE = re.compile(r"<[a-zA-Z][\s\S]*?>")

def looks_like_html(s: str) -> bool:
    """Detect if a string contains HTML tags."""
    return bool(s and _HTML_TAG_RE.search(s))


def extract_body_if_full_doc(html_doc: str) -> str:
    """
    If user pasted a full HTML document, extract the <body>...</body>.
    Otherwise return as-is.
    """
    if not html_doc:
        return ""
    m = re.search(r"<body[^>]*>(.*)</body>", html_doc, re.I | re.S)
    return m.group(1).strip() if m else html_doc


# ----------------------------
# 1) Build branded email HTML
# ----------------------------
def build_branded_email_html(user: dict, followup: dict) -> str:
    """
    Returns the FINAL HTML to send (branded shell + inner content).

    Rules:
      - email_format='text' is NOT handled here (use plain text sender).
      - email_format='html' (default):
          * if message_override exists:
              - if it contains HTML tags -> use it as HTML
              - else -> convert plain text to HTML
          * else -> use global scheduler template
      - email_format='raw':
          * message_override is treated as HTML always (unescape + extract <body> if present)
          * if message_override is empty -> fallback to global scheduler template
    """
    uid = user["id"]
    branding = get_branding(uid)

    format_type = (followup.get("email_format") or "html").strip().lower()
    override = (followup.get("message_override") or "").strip()

    # -------------------------
    # 1) Choose inner_html
    # -------------------------
    if override:
        # RAW means "my override is HTML"
        if format_type == "raw":
            override = _html.unescape(override)
            inner_html = extract_body_if_full_doc(override)

        # HTML mode: accept either plain override or HTML override
        else:
            if looks_like_html(override):
                override = _html.unescape(override)
                inner_html = extract_body_if_full_doc(override)
            else:
                inner_html = plain_to_html(override)

    else:
        # No override: use saved scheduler template
        tpl = (get_scheduler_template(uid) or "").strip()
        if not tpl:
            tpl = """
<div style="font-family:Arial,sans-serif; font-size:14px; color:#111;">
  <p>Hi {{name}},</p>
  <p>Just a quick reminder about {{type}}.</p>
  {% if description %}<p>{{description}}</p>{% endif %}
  {% if due_date %}<p><b>Due date:</b> {{due_date}}</p>{% endif %}
  <p>Thanks,<br>{{sender}}</p>
  {% if footer %}
    <hr>
    <small style="color:#64748b;">{{footer}}</small>
  {% endif %}
</div>
""".strip()

        inner_html = render_scheduler_html(tpl, user, followup, branding)

    # -------------------------
    # 2) Headline + wrap
    # -------------------------
    followup_type = followup.get("followup_type") or "Follow-up"
    headline = f"Follow-up: {followup_type}"

    return render_followup_email_html(
        # company_name=branding.get("company_name") or "FollowUp Tracker",
        brand_color=branding.get("brand_color") or "#36A2EB",
        brand_logo=branding.get("brand_logo") or "",
        support_email=branding.get("support_email") or "",
        custom_footer=branding.get("custom_footer") or "",
        headline=headline,
        client_name=followup.get("client_name") or "",
        message_html=inner_html,
    )
# ----------------------------
# 2) Send branded HTML via Gmail
# ----------------------------
def send_branded_email_gmail(user: dict, to_email: str, subject: str, html_body: str) -> str:
    """
    Sends HTML email via Gmail API.
    Uses multipart/alternative so Gmail renders HTML reliably.
    """
    to_email = (to_email or "").strip()
    if not to_email:
        raise ValueError("Missing recipient email")

    subject = subject or "(no subject)"
    html_body = html_body or ""

    msg = MIMEMultipart("alternative")
    msg["To"] = to_email
    msg["Subject"] = subject
    msg["From"] = "me"

    # Plain fallback is important
    msg.attach(MIMEText("This email requires an HTML-capable client.", "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

    creds = _creds_from_user(user)
    service = build("gmail", "v1", credentials=creds)

    sent = service.users().messages().send(
        userId="me",
        body={"raw": raw}
    ).execute()

    _save_refreshed_token(user["id"], creds)
    return sent.get("id")
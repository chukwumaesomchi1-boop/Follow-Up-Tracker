# send_via_preference.py

from __future__ import annotations

import re
from flask import current_app
import textwrap

from email_renderer import render_followup_email_html, plain_to_html
from gmail_sync import send_email_gmail  # your Gmail sender
from models_saas import get_branding

# -----------------------------
# Phone helpers
# -----------------------------
_E164_RE = re.compile(r"^\+\d{8,15}$")


from email.mime.text import MIMEText
import base64
from googleapiclient.discovery import build

# ---------- Placeholder helpers ----------


from gmail_sync import  _creds_from_user


def _save_refreshed_token(user_id, creds):
    """
    Save refreshed OAuth token if needed.
    Replace with your token persistence logic.
    """
    pass

# ---------- True plain-text sender ----------

import base64
from email.mime.text import MIMEText
from googleapiclient.discovery import build


def send_plain_text_email(user: dict, to_email: str, subject: str, body: str):
    """
    Sends true plain-text email via Gmail API.
    Preserves EXACT structure as typed.
    """

    to_email = (to_email or "").strip()
    if not to_email:
        raise ValueError("Missing recipient email")

    # Normalize line endings ONLY (do not modify content)
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    body = body.replace("\n", "\r\n")

    # 🔎 DEBUG: See EXACT raw body being sent
    print("RAW BODY BEING SENT:")
    print(repr(body))

    msg = MIMEText(body or "", "plain", "utf-8")
    msg["to"] = to_email
    msg["subject"] = subject or "(no subject)"

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

    creds = _creds_from_user(user)
    service = build("gmail", "v1", credentials=creds)

    sent = service.users().messages().send(
        userId="me",
        body={"raw": raw}
    ).execute()

    _save_refreshed_token(user["id"], creds)

    return sent.get("id")


from email.mime.text import MIMEText
import base64
from googleapiclient.discovery import build

def format_plain_text_message(raw_message: str) -> str:
    """
    Takes a raw string and formats it for plain-text email:
    - Adds paragraph breaks
    - Converts list items starting with '-' or '*' into bullet points
    - Ensures spacing between sections
    """
    if not raw_message:
        return ""

    lines = raw_message.splitlines()
    formatted_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            # preserve blank lines for paragraph breaks
            formatted_lines.append("")
        elif stripped.startswith(("-", "*")):
            # convert hyphen/asterisk to bullet point
            formatted_lines.append(f"• {stripped[1:].strip()}")
        else:
            formatted_lines.append(stripped)

    # Combine lines and ensure double line breaks between paragraphs
    final_message = "\n".join(formatted_lines)
    return final_message




def normalize_phone(phone: str) -> str:
    p = (phone or "").strip()

    # remove invisible junk + common formatting
    p = p.replace("\u00A0", "")  # non-breaking space
    p = p.replace("\u200B", "")  # zero-width space
    p = p.replace(" ", "").replace("-", "")
    p = p.replace("(", "").replace(")", "")

    # remove accidental whatsapp: prefix if user pasted it
    if p.lower().startswith("whatsapp:"):
        p = p.split(":", 1)[1].strip()

    # Nigeria local formats -> E.164
    # 080xxxxxxxxxx -> +23480xxxxxxxxx
    if re.fullmatch(r"0\d{10}", p):
        p = "+234" + p[1:]

    # 234xxxxxxxxxx -> +234xxxxxxxxxx
    if re.fullmatch(r"234\d{10}", p):
        p = "+" + p

    return p


def is_valid_phone_e164(phone: str) -> bool:
    p = normalize_phone(phone)
    return bool(_E164_RE.fullmatch(p))

from markupsafe import escape

import html

def plain_to_html(text: str) -> str:
    if not text:
        return ""

    # Normalize line endings
    text = text.replace("\r\n", "\n").strip()

    paragraphs = text.split("\n\n")

    html_parts = []
    for p in paragraphs:
        safe = html.escape(p).replace("\n", "<br>")
        html_parts.append(
            f"<p style='margin:0 0 16px 0; line-height:1.6; font-size:14px; color:#334155;'>{safe}</p>"
        )

    return "".join(html_parts)


# -----------------------------
# Email sender wrapper
# -----------------------------
# def send_email(user: dict, to_email: str, subject: str, body_html: str) -> None:
#     msg_id = send_email_gmail(user=user, to_email=to_email, subject=subject, html_body=body_html)
#     try:
#         current_app.logger.warning(f"[GMAIL] sent message id={msg_id}")
#     except Exception:
#         # allow usage outside request/app context
#         pass


from email.mime.text import MIMEText
import base64
from googleapiclient.discovery import build
from flask import render_template_string

def send_email(user: dict, to_email: str, subject: str, body: str, *, is_html=False):
    """
    Sends an email via Gmail API. Handles plain text, branded HTML, or raw HTML.
    """
    to_email = (to_email or "").strip()
    if not to_email:
        raise ValueError("Missing recipient email")

    # Decide MIME type
    mime_type = "html" if is_html else "plain"

    # If HTML, render any template variables
    if is_html:
        body = render_template_string(body, user=user)

    # Normalize line endings for plain text only
    if not is_html:
        body = body.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")

    msg = MIMEText(body or "", mime_type, "utf-8")
    msg["to"] = to_email
    msg["subject"] = subject or "(no subject)"
    msg["from"] = user.get("email") or "me"

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

    creds = _creds_from_user(user)
    service = build("gmail", "v1", credentials=creds)

    sent = service.users().messages().send(
        userId="me",
        body={"raw": raw}
    ).execute()

    _save_refreshed_token(user["id"], creds)

    return sent.get("id")


def send_followup_email(user: dict, f: dict, message: str) -> bool:
    to_email = (f.get("email") or "").strip()
    if not to_email:
        raise RuntimeError("Missing recipient email")

    subject = f"Follow-up: {f.get('followup_type') or 'follow-up'}"
    email_format = (f.get("email_format") or "html").lower()

    if email_format == "text":
        send_plain_text_email(user, to_email, subject, message)
    else:
        # raw HTML or branded HTML, just use the send_email wrapper
        send_email(user, to_email, subject, message, is_html=True)

    return True

# -----------------------------
# Main dispatcher
# -----------------------------

# def send_via_preference(user: dict, f: dict, message: str):
#     """
#     Sends a message via the user's preferred channel.

#     Returns:
#         (channel_used: str|None, error: str|None)

#     Notes:
#     - message is plain text for WhatsApp/SMS
#     - for Email, supports:
#         1. Plain text (email_format='text')
#         2. Branded HTML template (default)
#         3. Raw HTML (email_format='raw')
#     """
#     print("MESSAGE BEFORE DISPATCH:", repr(message))

#     channel = (f.get("preferred_channel") or "whatsapp").strip().lower()

#     # -------- Email --------
#     if channel == "email":
#         email = (f.get("email") or "").strip()
#         if not email:
#             return None, "Preferred channel is Email but email is missing."

#         subject = f"Follow-up: {f.get('followup_type', 'follow-up')}"
#         format_type = (f.get("email_format") or "html").strip().lower()

#         branding = get_branding(user.get("id"))

#         # Raw HTML mode (send exactly what user wrote)
#         if format_type == "raw":
#             print("[DEBUG] Sending as RAW HTML")
#             send_email(user, email, subject, message, is_html=True)

#         # Plain text (smart formatting)
#         elif format_type == "text":
#             print("[DEBUG] Sending as PLAIN TEXT email")
#             print("[DEBUG] To:", email)
#             print("[DEBUG] Subject:", subject)
#             print("[DEBUG] Body repr:", repr(message))
#             send_plain_text_email(user, email, subject, message)

#         # Default: HTML template
#         else:
#             print("[DEBUG] Sending as BRANDED HTML")
#             html_body = render_followup_email_html(
#                 brand_name="FollowUp Tracker",
#                 brand_color=branding.get("brand_color") or "#36A2EB",
#                 logo_url=branding.get("brand_logo") or "",
#                 headline="Quick follow-up",
#                 message_html=plain_to_html(message),
#                 client_name=f.get("client_name") or "",
#             )
#             send_email(user, email, subject, html_body, is_html=True)

#         return "Email", None

#     # -------- WhatsApp / SMS fallback --------
#     elif channel in ("whatsapp", "sms"):
#         print(f"[DEBUG] Sending via {channel.upper()}")
#         # send_whatsapp(user, f, message)  # placeholder
#         return channel.capitalize(), None

#     return None, f"Unknown preferred channel: {channel}"

import logging
import sys

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.propagate = True  # make sure it bubbles up to root

if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)


import logging
import sys

# --- Core logger setup ---
logging.basicConfig(
    level=logging.DEBUG,                 # capture debug/info/warnings/errors
    format='[%(asctime)s] [%(levelname)s] %(name)s: %(message)s',
    stream=sys.stdout                    # force output to console (Render sees it)
)

logger = logging.getLogger(__name__)  


def send_via_preference(user: dict, f: dict, message: str):
    """
    Sends a message via the user's preferred channel.

    Returns:
        (channel_used: str|None, error: str|None)

    Notes:
    - message is plain text for WhatsApp/SMS
    - for Email, supports:
        1. Plain text (email_format='text')
        2. Branded HTML template (default)
        3. Raw HTML (email_format='raw')
    """
    logger.debug("MESSAGE BEFORE DISPATCH: %r", message)

    channel = (f.get("preferred_channel") or "whatsapp").strip().lower()
    logger.debug("Resolved channel: %s", channel)

    # -------- Email --------
    if channel == "email":
        email = (f.get("email") or "").strip()
        if not email:
            logger.warning("Preferred channel is Email but email is missing.")
            return None, "Preferred channel is Email but email is missing."

        subject = f"Follow-up: {f.get('followup_type', 'follow-up')}"
        format_type = (f.get("email_format") or "html").strip().lower()
        branding = get_branding(user.get("id"))

        if format_type == "raw":
            logger.debug("[DEBUG] Sending as RAW HTML to %s", email)
            send_email(user, email, subject, message, is_html=True)

        elif format_type == "text":
            logger.debug("[DEBUG] Sending as PLAIN TEXT email to %s", email)

            formatted = format_plain_text_message(message)

            logger.debug("Formatted Body: %r", formatted)
            
            send_plain_text_email(user, email, subject, message)

        else:  # default: branded HTML
            logger.debug("[DEBUG] Sending as BRANDED HTML to %s", email)
            html_body = render_followup_email_html(
                brand_name="FollowUp Tracker",
                brand_color=branding.get("brand_color") or "#36A2EB",
                logo_url=branding.get("brand_logo") or "",
                headline="Quick follow-up",
                message_html=plain_to_html(message),
                client_name=f.get("client_name") or "",
            )
            send_email(user, email, subject, html_body, is_html=True)

        return "Email", None

    # -------- WhatsApp / SMS fallback --------
    elif channel in ("whatsapp", "sms"):
        logger.debug("Sending via %s", channel.upper())
        # send_whatsapp(user, f, message)  # placeholder
        return channel.capitalize(), None

    logger.error("Unknown preferred channel: %s", channel)
    return None, f"Unknown preferred channel: {channel}"
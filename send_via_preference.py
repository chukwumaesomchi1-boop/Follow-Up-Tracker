# send_via_preference.py

from __future__ import annotations

import re
from flask import current_app

from email_renderer import render_followup_email_html, plain_to_html
from gmail_sync import send_email_gmail  # your Gmail sender
from models_saas import get_branding

# -----------------------------
# Phone helpers
# -----------------------------
_E164_RE = re.compile(r"^\+\d{8,15}$")


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


def send_email(user: dict, to_email: str, subject: str, body: str, is_html=False) -> None:
    msg_id = send_email_gmail(
        user=user,
        to_email=to_email,
        subject=subject,
        body=body,
        is_html=is_html
    )

    try:
        current_app.logger.warning(f"[GMAIL] sent message id={msg_id}")
    except Exception:
        pass


def send_followup_email(user: dict, f: dict, message: str) -> bool:
    """
    Sends a followup email using Gmail.
    Returns True on success. Raises on failure.
    """
    to_email = (f.get("email") or "").strip()
    if not to_email:
        raise RuntimeError("Missing recipient email")

    subject = f"Follow-up: {f.get('followup_type') or 'follow-up'}"

    # If send_email_gmail throws -> we fail (good)
    result = send_email_gmail(
        user=user,
        to_email=to_email,
        subject=subject,
        html_body=message,
    )

    # If your send_email_gmail returns something meaningful, enforce it:
    if result is False:
        raise RuntimeError("send_email_gmail returned False")

    return True

# -----------------------------
# Main dispatcher
# -----------------------------
# def send_via_preference(user: dict, f: dict, message: str):
#     """
#     Returns: (channel_used: str|None, error: str|None)
#     - message is plain text for WhatsApp/SMS
#     - for Email: we render a branded HTML template by default
#       OR if f['email_mode']=='raw', we treat message as raw HTML.
#     """
#     channel = (f.get("preferred_channel") or "whatsapp").strip().lower()

#     # -------- Email --------
#     if channel == "email":
#         email = (f.get("email") or "").strip()
#         if not email:
#             return None, "Preferred channel is Email but email is missing."

#         subject = f"Follow-up: {f.get('followup_type', 'follow-up')}"

#         # Raw HTML email path
#         if (f.get("email_mode") or "").strip().lower() == "raw":
#             if "<" not in message or ">" not in message: 
#                 message = plain_to_html(message)
#             send_email(user, email, subject, message)
#             return "Email", None

#         branding = get_branding(user.get("id"))

#         html_body = render_followup_email_html(
#             brand_name="FollowUp Tracker",
#             brand_color=branding.get("brand_color") or "#36A2EB",
#             logo_url=branding.get("brand_logo") or "",
#             headline="Quick follow-up",
#             message_html=plain_to_html(message),
#             client_name=f.get("client_name") or "",
#         )

#         send_email(user, email, subject, html_body)
#         return "Email", None

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
        3. Raw HTML (email_mode='raw')
    """
    channel = (f.get("preferred_channel") or "whatsapp").strip().lower()

    # -------- Email --------
    if channel == "email":
        email = (f.get("email") or "").strip()
        if not email:
            return None, "Preferred channel is Email but email is missing."

        subject = f"Follow-up: {f.get('followup_type', 'follow-up')}"
        format_type = (f.get("email_format") or "html").strip().lower()
        email_mode  = (f.get("email_mode") or "").strip().lower()

        branding = get_branding(user.get("id"))

        # Raw HTML mode (send exactly what user wrote)
        if email_mode == "raw":
            send_email(user, email, subject, message, is_html=True)

        # Plain text
        elif format_type == "text":
            send_email(user, email, subject, message, is_html=False)

        # Default: HTML template
        else:
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
    # (you can expand this with your actual sending logic)
    elif channel in ("whatsapp", "sms"):
        # send_whatsapp(user, f, message)  # placeholder
        return channel.capitalize(), None

    return None, f"Unknown preferred channel: {channel}"

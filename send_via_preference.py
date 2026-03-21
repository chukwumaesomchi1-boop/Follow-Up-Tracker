# send_via_preference.py

from __future__ import annotations

import re
from flask import current_app
import textwrap


from gmail_sync import send_email_gmail  # your Gmail sender
from models_saas import get_branding
from email_scheduler import send_branded_email_gmail
from email_scheduler import build_branded_email_html

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
    Preserve plain-text email exactly as the user typed it,
    while only normalizing line endings for safe sending.
    """
    if not raw_message:
        return ""

    # Normalize line endings only
    text = raw_message.replace("\r\n", "\n").replace("\r", "\n")

    # Preserve all paragraph breaks and spacing exactly
    return text



from typing import Dict, Optional

import html
from flask import current_app

def plain_text_to_email_html_body(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()

    if not text:
        html_body = "<p style='margin:0; color:#334155; font-size:15px; line-height:1.7;'>&nbsp;</p>"
        current_app.logger.warning("FULL TEXT HTML BODY: %r", html_body[:1200])
        return html_body

    paragraphs = text.split("\n\n")
    parts = []

    for p in paragraphs:
        safe = html.escape(p).replace("\n", "<br>")
        parts.append(
            f"<p style='margin:0 0 16px 0; color:#334155; font-size:15px; line-height:1.7;'>{safe}</p>"
        )

    html_body = "".join(parts)

    current_app.logger.warning("FULL TEXT HTML BODY: %r", html_body[:1200])

    return html_body

import html


import html
from flask import current_app

# def render_text_email_html(user: dict, followup: dict, raw_text: str, branding: dict) -> str:
#     current_app.logger.warning("USING render_text_email_html v2")

#     safe = html.escape(raw_text or "").replace("\r\n", "\n").replace("\r", "\n")
#     safe = safe.replace("\n\n", "</p><p>").replace("\n", "<br>")

#     return f"""
#     <html>
#       <body style="background:#ffefef; margin:0; padding:40px;">
#         <table width="100%" cellpadding="0" cellspacing="0" border="0">
#           <tr>
#             <td align="center">
#               <table width="600" cellpadding="0" cellspacing="0" border="0" style="background:#ffffff; border:4px solid red;">
#                 <tr>
#                   <td style="padding:40px;">
#                     <h1 style="color:blue; margin-top:0;">HTML TEST SHELL</h1>
#                     <p>{safe}</p>
#                   </td>
#                 </tr>
#               </table>
#             </td>
#           </tr>
#         </table>
#       </body>
#     </html>
#     """


import html

import html

def plain_text_to_email_html_body(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()

    if not text:
        return "<p style='margin:0 0 16px 0;'>&nbsp;</p>"

    paragraphs = text.split("\n\n")
    html_parts = []

    for p in paragraphs:
        safe = html.escape(p).replace("\n", "<br>")
        html_parts.append(
            f"<p style='margin:0 0 16px 0; color:#334155; font-size:15px; line-height:1.7;'>{safe}</p>"
        )

    return "".join(html_parts)


import html
from typing import Dict, Any
from urllib.parse import urljoin
from flask import request, has_request_context

def absolute_asset_url(path: str) -> str:
    path = (path or "").strip()
    if not path:
        return ""

    if path.startswith("http://") or path.startswith("https://"):
        return path

    if has_request_context():
        return urljoin(request.host_url, path.lstrip("/"))

    return urljoin("https://follow-up-tracker.onrender.com/", path.lstrip("/"))

def render_text_email_html(user: Dict, followup: Dict, raw_text: str, branding: Dict) -> str:
    """
    Renders a polished, responsive HTML email based on branding and message content.
    """
    # 1. Extraction & Defaults
    company_name = (branding.get("company_name") or "Your Company").strip()
    brand_logo = absolute_asset_url(branding.get("brand_logo") or "").strip()
    support_email = (branding.get("support_email") or "").strip()
    
    # Safely escape text for attributes/content
    safe_company = html.escape(company_name)
    
    # 2. Content Preparation (Helper function logic assumed or integrated)
    # If plain_text_to_email_html_body handles escaping, use it here.
    # Otherwise, ensure raw_text is escaped and line breaks are converted to <br>.
    message_html = f'<div style="white-space: pre-wrap;">{html.escape(raw_text)}</div>'

    # 3. Component Construction
    logo_block = ""
    if brand_logo:
        logo_block = f"""
        <tr>
          <td align="center" style="padding: 40px 0 24px 0;">
            <img src="{brand_logo}" alt="{safe_company}" style="display:block; max-width:140px; height:auto; border:0;">
          </td>
        </tr>
        """
    else:
        # Fallback to a styled text-based header if logo is missing
        logo_block = f"""
        <tr>
          <td align="center" style="padding: 40px 0 24px 0;">
            <span style="font-size: 24px; font-weight: 700; color: #1e293b; letter-spacing: -0.025em;">{safe_company}</span>
          </td>
        </tr>
        """

    footer_content = (
        f'Questions? Contact <a href="mailto:{support_email}" style="color:#6366f1; text-decoration:none;">{html.escape(support_email)}</a>'
        if support_email else "Please do not reply directly to this email."
    )

    # 4. The Modern Template
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_company} - Update</title>
  <style>
    @media screen and (max-width: 600px) {{
      .container {{ width: 100% !important; }}
      .content-cell {{ padding: 24px !important; }}
    }}
  </style>
</head>
<body style="margin:0; padding:0; background-color:#f1f5f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#f1f5f9; table-layout:fixed;">
    <tr>
      <td align="center" style="padding: 20px 10px;">
        <table class="container" width="600" cellpadding="0" cellspacing="0" border="0" style="width:600px; max-width:600px;">
          
          {logo_block}

          <tr>
            <td class="content-cell" style="background:#ffffff; padding:48px; border-radius:12px; border:1px solid #e2e8f0; box-shadow: 0 1px 3px 0 rgba(0,0,0,0.1);">
              <div style="font-size:16px; line-height:1.6; color:#334155;">
                {message_html}
              </div>
            </td>
          </tr>

          <tr>
            <td align="center" style="padding:32px 20px;">
              <p style="margin:0; font-size:13px; line-height:1.6; color:#64748b;">
                &copy; 2026 <strong>{safe_company}</strong>. All rights reserved.<br>
                {footer_content}
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>""".strip()

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

# def send_email(user: dict, to_email: str, subject: str, body: str, *, is_html=False):
#     """
#     Sends an email via Gmail API. Handles plain text, branded HTML, or raw HTML.
#     """
#     to_email = (to_email or "").strip()
#     if not to_email:
#         raise ValueError("Missing recipient email")

#     # Decide MIME type
#     mime_type = "html" if is_html else "plain"

#     # If HTML, render any template variables
#     if is_html:
#         body = render_template_string(body, user=user)

#     # Normalize line endings for plain text only
#     if not is_html:
#         body = body.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")

#     # Debug logging for body inspection
#     logger.debug("HTML startswith: %r", body[:120])
#     logger.debug("Contains &lt; ? %s", "&lt;" in body)
#     logger.debug("Contains real < ? %s", "<" in body)

#     msg = MIMEText(body or "", mime_type, "utf-8")
#     msg["to"] = to_email
#     msg["subject"] = subject or "(no subject)"
#     msg["from"] = user.get("email") or "me"

#     raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

#     creds = _creds_from_user(user)
#     service = build("gmail", "v1", credentials=creds)

#     sent = service.users().messages().send(
#         userId="me",
#         body={"raw": raw}
#     ).execute()

#     _save_refreshed_token(user["id"], creds)

#     return sent.get("id")


from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import base64
from googleapiclient.discovery import build

def send_email(user: dict, to_email: str, subject: str, body: str, *, is_html: bool = False):
    """
    Sends an email via Gmail API.
    - is_html=False -> sends text/plain
    - is_html=True  -> sends multipart/alternative with text/plain + text/html (Gmail renders HTML reliably)
    """
    to_email = (to_email or "").strip()
    if not to_email:
        raise ValueError("Missing recipient email")

    subject = subject or "(no subject)"
    body = body or ""

    if is_html:
        # Multipart alternative: Gmail reliably renders the HTML part
        msg = MIMEMultipart("alternative")
        msg["To"] = to_email
        msg["Subject"] = subject
        msg["From"] = "me"
        msg["MIME-Version"] = "1.0"

        # Plain fallback (important: MUST NOT be empty)
        plain_fallback = "This email contains an HTML message. If you can't view it, try another email client."
        msg.attach(MIMEText(plain_fallback, "plain", "utf-8"))

        # HTML part
        msg.attach(MIMEText(body, "html", "utf-8"))

    else:
        # True plain-text email
        body = body.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
        msg = MIMEText(body, "plain", "utf-8")
        msg["To"] = to_email
        msg["Subject"] = subject
        msg["From"] = "me"
        msg["MIME-Version"] = "1.0"

    # Encode for Gmail API
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

    creds = _creds_from_user(user)
    service = build("gmail", "v1", credentials=creds)

    sent = service.users().messages().send(
        userId="me",
        body={"raw": raw}
    ).execute()

    _save_refreshed_token(user["id"], creds)
    return sent.get("id")



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
import html as _html
import re

def _extract_html_body(html_doc: str) -> str:
    """
    Gmail can be weird when you send a full HTML document.
    This extracts the inner <body>...</body> if present.
    If not present, returns the original string.
    """
    if not html_doc:
        return ""

    m = re.search(r"<body[^>]*>(.*)</body>", html_doc, re.I | re.S)
    return m.group(1).strip() if m else html_doc


import html as _html
import time
def send_via_preference(user: dict, f: dict, message: str):
    """
    Sends a message via the user's preferred channel.

    Email supports:
      1) Plain text  (email_format='text')  -> true text email
      2) Branded HTML (email_format='html') -> branded shell + scheduler/override
      3) Raw override (email_format='raw')  -> branded shell + message_override treated as HTML
         NOTE: raw does NOT change global template. It only affects this followup.
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

        subject = f"HTML TEST {int(time.time())}"
        format_type = (f.get("email_format") or "html").strip().lower()

        # -------- PLAIN TEXT --------
        if format_type == "text":
            logger.debug("[EMAIL] Sending text-preserved email inside branded HTML shell to %s", email)

            formatted = format_plain_text_message(message or "")
            branding = get_branding(user.get("id")) or {}
            html_body = render_text_email_html(user, f, formatted, branding)

            logger.debug("[EMAIL] Text Body first 120 chars: %r", formatted[:120])
            logger.debug("[EMAIL] Text HTML first 120 chars: %r", (html_body or "")[:120])
            
            send_branded_email_gmail(user, email, subject, html_body)
            return "Email", None

        # -------- BRANDED HTML (html + raw) --------
        # raw just means: message_override is expected to contain HTML (override per-followup)
        logger.debug("[EMAIL] Sending as BRANDED HTML (%s) to %s", format_type, email)

        # IMPORTANT:
        # build_branded_email_html() must read followup["message_override"] from DB.
        # So f should already contain message_override.
        # If your "message" param is the override, ensure f["message_override"] = message before calling build.
        if message and not (f.get("message_override") or "").strip():
            # make sure builder sees the override (in case caller didn't store it yet)
            f = dict(f)
            f["message_override"] = message

        html_body = build_branded_email_html(user, f)

        logger.debug("[EMAIL] HTML first 120 chars: %r", (html_body or "")[:120])

        send_branded_email_gmail(user, email, subject, html_body)
        return "Email", None

    # -------- WhatsApp / SMS fallback --------
    if channel in ("whatsapp", "sms"):
        logger.debug("Sending via %s", channel.upper())
        return channel.capitalize(), None

    logger.error("Unknown preferred channel: %s", channel)
    return None, f"Unknown preferred channel: {channel}"
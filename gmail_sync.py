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

# def check_replies_for_user(user: dict, email: str = None):
#     service = _service_for_user(user)
#     ...

import os
import json
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import warnings
from flask import render_template_string

# Suppress ADC warning completely
warnings.filterwarnings(
    "ignore",
    message="Your default credentials were not found"
)

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

# -------------------------
# Helper: build credentials from stored user token
# -------------------------
# def _creds_from_user(user: dict) -> Credentials:
#     token_json = (user.get("gmail_token") or "").strip()
#     if not token_json:
#         raise Exception("Gmail not connected")

#     try:
#         info = json.loads(token_json)
#     except Exception:
#         raise Exception("Gmail token is corrupted (not valid JSON). Reconnect Gmail.")

#     creds = Credentials.from_authorized_user_info(info, SCOPES)

#     # Refresh if expired
#     if not creds.valid:
#         if creds.expired and creds.refresh_token:
#             creds.refresh(Request())
#         else:
#             raise Exception("Gmail access expired or missing refresh_token. Reconnect Gmail.")

#     return creds


from models_saas import *
import json
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from flask import render_template_string
# fresh_user = get_user_by_id(user["id"]) 
def _creds_from_user(user: dict) -> Credentials:
    """
    Reconstruct a Credentials object from the saved Gmail token in the database.
    Automatically refreshes if expired.
    """
    token_json = user.get("gmail_token")
    if not token_json:
        raise Exception("User has no saved Gmail token. Connect Gmail first.")

    data = json.loads(token_json)

    creds = Credentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=data.get("client_id") or os.getenv("GOOGLE_OAUTH_CLIENT_ID"),
        client_secret=data.get("client_secret") or os.getenv("GOOGLE_OAUTH_CLIENT_SECRET"),
        scopes=data.get("scopes"),
    )

    # Refresh if expired
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise Exception("Gmail access expired or missing refresh_token. Reconnect Gmail.")

    return creds




def _save_refreshed_token(user_id: int, creds: Credentials) -> None:
    # Directly call your existing function
    save_gmail_token(user_id, creds.to_json())


def send_email_gmail(user: dict, to_email: str, subject: str, body: str, *, is_html=False):
    to_email = (to_email or "").strip()
    if not to_email:
        raise ValueError("Missing recipient email")

    # Decide MIME type
    mime_type = "html" if is_html else "plain"

    # Render template if HTML
    if is_html:
        body = render_template_string(body, user=user)

    # Normalize line endings for plain text
    if not is_html:
        body = body.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")

    # Create message
    if is_html:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(body or "", "html", "utf-8"))
    else:
        msg = MIMEText(body or "", "plain", "utf-8")

    msg["to"] = to_email
    msg["subject"] = subject or "(no subject)"
    msg["from"] = user.get("email") or "me"

    # Encode for Gmail API
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

    # Build Gmail service using reconstructed creds
    creds = _creds_from_user(user)
    service = build("gmail", "v1", credentials=creds)

    sent = service.users().messages().send(
        userId="me",
        body={"raw": raw}
    ).execute()

    # Save refreshed token back
    _save_refreshed_token(user["id"], creds)

    return sent.get("id")
# -------------------------
# Helper: save refreshed token
# -------------------------
# def _save_refreshed_token(user_id: int, creds: Credentials):
#     from models_saas import update_gmail_token
#     update_gmail_token(user_id, creds.to_json())

# -------------------------
# Helper: Gmail service for a user
# -------------------------
def _service_for_user(user: dict):
    creds = _creds_from_user(user)
    return build("gmail", "v1", credentials=creds)

# -------------------------
# Send email via Gmail (plain text or HTML)
# -------------------------
# def send_email_gmail(user: dict, to_email: str, subject: str, body: str, *, is_html=False):
#     to_email = (to_email or "").strip()
#     if not to_email:
#         raise ValueError("Missing recipient email")

#     # Decide MIME type
#     mime_type = "html" if is_html else "plain"

#     # Render template if HTML
#     if is_html:
#         body = render_template_string(body, user=user)

#     # Normalize line endings for plain text
#     if not is_html:
#         body = body.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")

#     # Create message
#     if is_html:
#         msg = MIMEMultipart("alternative")
#         msg.attach(MIMEText(body or "", "html", "utf-8"))
#     else:
#         msg = MIMEText(body or "", "plain", "utf-8")

#     msg["to"] = to_email
#     msg["subject"] = subject or "(no subject)"
#     msg["from"] = user.get("email") or "me"

#     # Encode for Gmail API
#     raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

#     # Send email
#     creds = _creds_from_user(user)
#     service = build("gmail", "v1", credentials=creds)

#     sent = service.users().messages().send(
#         userId="me",
#         body={"raw": raw}
#     ).execute()

#     _save_refreshed_token(user["id"], creds)
#     return sent.get("id")

# -------------------------
# Optional helper to check replies
# -------------------------
def check_replies_for_user(user: dict, email: str = None):
    service = _service_for_user(user)
    ...
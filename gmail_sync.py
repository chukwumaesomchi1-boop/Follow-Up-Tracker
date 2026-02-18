import os
import json
import base64
from email.mime.text import MIMEText

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If you also want to connect accounts from the web app:
from google_auth_oauthlib.flow import Flow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
]

CREDS_PATH = os.getenv("GOOGLE_CREDENTIALS") or "credentials.json"


def _creds_from_user(user: dict) -> Credentials:
    """
    Build Credentials from what's stored in users.gmail_token (JSON string).
    """
    token_json = (user.get("gmail_token") or "").strip()
    if not token_json:
        raise Exception("Gmail not connected")

    try:
        info = json.loads(token_json)
    except Exception:
        raise Exception("Gmail token is corrupted (not valid JSON). Reconnect Gmail.")

    creds = Credentials.from_authorized_user_info(info, SCOPES)

    # refresh if needed
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise Exception("Gmail access expired or missing refresh_token. Reconnect Gmail.")

    return creds


def _service_for_user(user: dict):
    creds = _creds_from_user(user)
    return build("gmail", "v1", credentials=creds)


def _save_refreshed_token(user_id: int, creds: Credentials):
    """
    You MUST implement this in models_saas:
      update_gmail_token(user_id, creds.to_json())
    """
    from models_saas import update_gmail_token
    update_gmail_token(user_id, creds.to_json())


def send_email_gmail(user: dict, to_email: str, subject: str, html_body: str):
    """
    Sends HTML email via Gmail API using the connected user's Gmail.
    Returns Gmail message id.
    """
    to_email = (to_email or "").strip()
    if not to_email:
        raise ValueError("Missing recipient email")

    creds = _creds_from_user(user)

    # Build MIME
    msg = MIMEText(html_body or "", "html", "utf-8")
    msg["to"] = to_email
    msg["subject"] = subject or "(no subject)"

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

    try:
        service = build("gmail", "v1", credentials=creds)
        sent = service.users().messages().send(
            userId="me",
            body={"raw": raw}
        ).execute()

        # Save refreshed token if it changed after refresh
        # (creds.to_json() always serializes latest access token)
        _save_refreshed_token(user["id"], creds)

        return sent.get("id")

    except HttpError as e:
        # revoked / unauthorized etc.
        # Common revoke: 401 invalid_grant
        raise Exception(f"Gmail API error: {e}")


# gmail_service.py or followups.py

def check_replies_for_user(user: dict, email: str = None):
    service = _service_for_user(user)
    ...

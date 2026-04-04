import os
import json
import base64
import warnings
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from flask import render_template_string

from models_saas import save_gmail_token

# kill annoying warning
warnings.filterwarnings(
    "ignore",
    message="Your default credentials were not found"
)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]

# -------------------------
# AUTH
# -------------------------
def _creds_from_user(user: dict) -> Credentials:
    token_json = user.get("gmail_token")
    if not token_json:
        raise Exception("Connect Gmail first.")

    data = json.loads(token_json)

    creds = Credentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=data.get("client_id") or os.getenv("GOOGLE_OAUTH_CLIENT_ID"),
        client_secret=data.get("client_secret") or os.getenv("GOOGLE_OAUTH_CLIENT_SECRET"),
        scopes=data.get("scopes"),
    )

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise Exception("Reconnect Gmail.")

    return creds


def _save_refreshed_token(user_id: int, creds: Credentials):
    save_gmail_token(user_id, creds.to_json())


def _service_for_user(user: dict):
    creds = _creds_from_user(user)
    return build("gmail", "v1", credentials=creds)


# -------------------------
# SEND EMAIL (ONLY ONE VERSION)
# -------------------------
# def send_email_gmail(user: dict, to_email: str, subject: str, body: str, *, is_html=False):
#     to_email = (to_email or "").strip()
#     if not to_email:
#         raise ValueError("Missing recipient email")

#     if is_html:
#         body = render_template_string(body, user=user)

#     if not is_html:
#         body = body.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")

#     if is_html:
#         msg = MIMEMultipart("alternative")
#         msg.attach(MIMEText(body or "", "html", "utf-8"))
#     else:
#         msg = MIMEText(body or "", "plain", "utf-8")

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

def send_email_gmail(user: dict, to_email: str, subject: str, body: str, *, is_html=False):
    to_email = (to_email or "").strip()
    if not to_email:
        raise ValueError("Missing recipient email")

    if is_html:
        body = render_template_string(body, user=user)

    if not is_html:
        body = body.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")

    if is_html:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(body or "", "html", "utf-8"))
    else:
        msg = MIMEText(body or "", "plain", "utf-8")

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

    return {
        "message_id": sent.get("id"),
        "thread_id": sent.get("threadId"),
    }


# -------------------------
# OPTIONAL (you'll expand later)
# -------------------------

from email.utils import parseaddr
from models_saas import (
    get_reply_tracked_followups,
    mark_followup_replied,
    disable_followup_schedule,
    add_notification,
)


def extract_email_address(header_value: str) -> str:
    _, addr = parseaddr(header_value or "")
    return (addr or "").strip().lower()


def check_replies_for_user(user: dict):
    service = _service_for_user(user)
    user_email = (user.get("email") or "").strip().lower()
    if not user_email:
        return []

    followups = get_reply_tracked_followups(user["id"])
    results = []

    for f in followups:
        thread_id = (f.get("gmail_thread_id") or "").strip()
        recipient_email = (f.get("email") or "").strip().lower()
        sent_message_id = (f.get("last_sent_message_id") or "").strip()

        if not thread_id or not recipient_email:
            continue

        try:
            thread = service.users().threads().get(
                userId="me",
                id=thread_id,
                format="full"
            ).execute()
        except Exception:
            continue

        messages = thread.get("messages") or []
        found_reply = None

        for msg in messages:
            msg_id = msg.get("id") or ""
            payload = msg.get("payload") or {}
            headers = {
                h["name"].lower(): h["value"]
                for h in (payload.get("headers") or [])
                if h.get("name") and h.get("value")
            }

            from_header = headers.get("from", "")
            from_email = extract_email_address(from_header)

            if not from_email:
                continue

            if msg_id == sent_message_id:
                continue

            if from_email == user_email:
                continue

            if from_email != recipient_email:
                continue

            found_reply = {
                "followup_id": f["id"],
                "reply_message_id": msg_id,
                "reply_from": from_header,
                "reply_subject": headers.get("subject", ""),
                "reply_date": headers.get("date", ""),
                "recipient_email": recipient_email,
            }
            break

        if not found_reply:
            continue

        mark_followup_replied(
            fid=f["id"],
            user_id=user["id"],
            reply_message_id=found_reply["reply_message_id"],
            reply_from=found_reply["reply_from"],
            reply_subject=found_reply["reply_subject"],
            reply_date=found_reply["reply_date"],
        )

        disable_followup_schedule(f["id"], user["id"])

        try:
            add_notification(
                user["id"],
                f"Reply detected from {recipient_email}. Auto-stopped follow-up #{f['id']}."
            )
        except Exception:
            pass

        results.append(found_reply)

    return results
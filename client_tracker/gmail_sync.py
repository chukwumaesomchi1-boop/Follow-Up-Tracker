import os
import pickle
import base64
from email.mime.text import MIMEText
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from models_saas import mark_followup_done_by_email

# Combined scopes for sending & modifying emails
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
]

TOKEN_PATH = "token.pickle"
CREDS_PATH = os.getenv("GOOGLE_CREDENTIALS") or "credentials.json"


def get_service():
    """Authenticate and return Gmail API service"""
    creds = None
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, "rb") as token_file:
            creds = pickle.load(token_file)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "wb") as token_file:
            pickle.dump(creds, token_file)

    service = build("gmail", "v1", credentials=creds)
    return service



import base64
from email.mime.text import MIMEText
from gmail_oauth import build_gmail_service

def send_email_gmail(user, to_email, subject, body):
    token = user["gmail_token"]
    if not token:
        raise Exception("Gmail not connected")




def check_replies(email: str = None):
    """
    Check unread Gmail messages.
    - If `email` is provided, only check messages from that sender.
    - If `email` is None, check all unread messages.
    Marks follow-ups done via `mark_followup_done_by_email`.
    """
    service = get_service()
    query = f"from:{email} is:unread" if email else "is:unread"

    results = service.users().messages().list(userId="me", q=query).execute()
    messages = results.get("messages", [])

    for msg in me



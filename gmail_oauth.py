import os
import json
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

def get_oauth_flow():
    creds_path = os.getenv("GOOGLE_CREDENTIALS", "credentials.json")
    flow = Flow.from_client_secrets_file(
        creds_path,
        scopes=SCOPES,
        redirect_uri=os.getenv("APP_BASE_URL") + "/gmail/callback",
    )
    return flow


def build_gmail_service(token_json: str):
    creds = Credentials.from_authorized_user_info(
        json.loads(token_json),
        scopes=SCOPES,
    )
    return build("gmail", "v1", credentials=creds)

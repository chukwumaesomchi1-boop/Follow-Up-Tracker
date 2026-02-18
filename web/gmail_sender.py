# Adapter so the rest of the app doesn't break
from client_tracker.gmail_sync import send_email_gmail


def send_email(user: dict, to_email: str, subject: str, html_body: str) -> None:
    return send_email_gmail(to_email, subject, body)

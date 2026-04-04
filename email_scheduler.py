import re
import html as _html
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from googleapiclient.discovery import build

from models_saas import get_scheduler_template, get_branding
from scheduler_render import render_scheduler_html

from gmail_sync import _creds_from_user, _save_refreshed_token
from scheduler_render import DEFAULT_SCHEDULER_TEMPLATE

_HTML_TAG_RE = re.compile(r"<[a-zA-Z][\s\S]*?>", re.I)




def build_branded_email_html(user: dict, followup: dict) -> str:
    """
    Build the final branded email HTML using the saved scheduler template.

    Option A:
    - Scheduler templates are FULL email templates
    - render_scheduler_html() returns the final HTML document
    - message_override is handled inside render_scheduler_html()
    - no extra wrapping is applied here
    """
    uid = user["id"]

    tmpl = (get_scheduler_template(uid) or "").strip()
    if not tmpl:
        tmpl = DEFAULT_SCHEDULER_TEMPLATE

    branding = get_branding(uid) or {}

    final_html = render_scheduler_html(
        tmpl=tmpl,
        user=user,
        followup=followup,
        branding=branding,
    )

    return (final_html or "").strip()



from email.message import EmailMessage
import base64
from googleapiclient.discovery import build

def send_branded_email_gmail(user: dict, to_email: str, subject: str, html_body: str) -> str:
    to_email = (to_email or "").strip()
    if not to_email:
        raise ValueError("Missing recipient email")

    subject = (subject or "(no subject)").strip()
    html_body = (html_body or "").strip()

    msg = EmailMessage()
    msg["To"] = to_email
    msg["Subject"] = subject
    msg["From"] = user.get("email") or "me"

    msg.set_content("This email contains an HTML message.")
    msg.add_alternative(html_body, subtype="html")

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
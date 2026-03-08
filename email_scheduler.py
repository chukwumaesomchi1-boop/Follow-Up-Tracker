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


# def looks_like_html(s: str) -> bool:
#     return bool(s and _HTML_TAG_RE.search(s))


# def is_full_html_document(s: str) -> bool:
#     if not s:
#         return False
#     s = s.strip().lower()
#     return (
#         s.startswith("<!doctype html")
#         or ("<html" in s and "</html>" in s)
#         or ("<body" in s and "</body>" in s)
#     )


# def extract_body_if_full_doc(html_doc: str) -> str:
#     """
#     If a full HTML document is pasted, return only the body contents.
#     Otherwise return the original string.
#     """
#     if not html_doc:
#         return ""

#     m = re.search(r"<body[^>]*>(.*)</body>", html_doc, re.I | re.S)
#     return m.group(1).strip() if m else html_doc.strip()


# def build_branded_email_html(user: dict, followup: dict) -> str:
#     """
#     Returns the FINAL HTML to send.

#     Rules:
#     - text mode is handled elsewhere
#     - raw mode:
#         message_override is treated as HTML
#     - html mode:
#         message_override may be plain text or HTML
#     - if no override:
#         use saved scheduler template
#         * if the rendered template is already a full HTML doc, send it directly
#         * otherwise wrap it with render_followup_email_html()
#     """
#     uid = user["id"]
#     branding = get_branding(uid)

#     format_type = (followup.get("email_format") or "html").strip().lower()
#     override = (followup.get("message_override") or "").strip()

#     # -----------------------------------
#     # 1) message_override takes priority
#     # -----------------------------------
#     if override:
#         if format_type == "raw":
#             override = _html.unescape(override)
#             if is_full_html_document(override):
#                 return override
#             inner_html = extract_body_if_full_doc(override)

#         else:
#             if looks_like_html(override):
#                 override = _html.unescape(override)
#                 if is_full_html_document(override):
#                     return override
#                 inner_html = extract_body_if_full_doc(override)
#             else:
#                 inner_html = plain_to_html(override)

#         followup_type = followup.get("followup_type") or "Follow-up"
#         headline = f"Follow-up: {followup_type}"

#         return render_followup_email_html(
#             brand_name=branding.get("company_name") or "FollowUp Tracker",
#             brand_color=branding.get("brand_color") or "#36A2EB",
#             logo_url=branding.get("brand_logo") or "",
#             support_email=branding.get("support_email") or "",
#             footer_note=branding.get("custom_footer") or "",
#             headline=headline,
#             client_name=followup.get("client_name") or "",
#             message_html=inner_html,
#         )

#     # -----------------------------------
#     # 2) No override -> use scheduler template
#     # -----------------------------------
#     tpl = (get_scheduler_template(uid) or "").strip()
#     if not tpl:
#         tpl = """
# <div style="font-family:Arial,sans-serif; font-size:14px; color:#111;">
#   <p>Hi {{name}},</p>
#   <p>Just a quick reminder about {{type}}.</p>
#   {% if description %}<p>{{description}}</p>{% endif %}
#   {% if due_date %}<p><b>Due date:</b> {{due_date}}</p>{% endif %}
#   <p>Thanks,<br>{{sender}}</p>
#   {% if footer %}
#     <hr>
#     <small style="color:#64748b;">{{footer}}</small>
#   {% endif %}
# </div>
# """.strip()

#     rendered_template = render_scheduler_html(tpl, user, followup, branding).strip()

#     # If the saved template is already a complete HTML email, return it directly.
#     if is_full_html_document(rendered_template):
#         return rendered_template

#     # Otherwise treat it as inner content and wrap it in your default shell.
#     followup_type = followup.get("followup_type") or "Follow-up"
#     headline = f"Follow-up: {followup_type}"

#     return render_followup_email_html(
#         brand_name=branding.get("company_name") or "FollowUp Tracker",
#         brand_color=branding.get("brand_color") or "#36A2EB",
#         logo_url=branding.get("brand_logo") or "",
#         support_email=branding.get("support_email") or "",
#         footer_note=branding.get("custom_footer") or "",
#         headline=headline,
#         client_name=followup.get("client_name") or "",
#         message_html=rendered_template,
#     )

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




def send_branded_email_gmail(user: dict, to_email: str, subject: str, html_body: str) -> str:
    """
    Sends HTML email via Gmail API.
    Uses multipart/alternative so Gmail renders HTML reliably.
    """
    to_email = (to_email or "").strip()
    if not to_email:
        raise ValueError("Missing recipient email")

    subject = subject or "(no subject)"
    html_body = html_body or ""

    msg = MIMEMultipart("alternative")
    msg["To"] = to_email
    msg["Subject"] = subject
    msg["From"] = "me"

    msg.attach(MIMEText("This email requires an HTML-capable client.", "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

    creds = _creds_from_user(user)
    service = build("gmail", "v1", credentials=creds)

    sent = service.users().messages().send(
        userId="me",
        body={"raw": raw}
    ).execute()

    _save_refreshed_token(user["id"], creds)
    return sent.get("id")



# def send_branded_email_gmail(user: dict, to_email: str, subject: str, html_body: str) -> str:
#     """
#     Sends HTML email via Gmail API.
#     Uses multipart/alternative so Gmail renders HTML reliably.
#     """
#     to_email = (to_email or "").strip()
#     if not to_email:
#         raise ValueError("Missing recipient email")

#     subject = subject or "(no subject)"
#     html_body = html_body or ""

#     msg = MIMEMultipart("alternative")
#     msg["To"] = to_email
#     msg["Subject"] = subject
#     msg["From"] = "me"

#     msg.attach(MIMEText("This email requires an HTML-capable client.", "plain", "utf-8"))
#     msg.attach(MIMEText(html_body, "html", "utf-8"))

#     raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

#     creds = _creds_from_user(user)
#     service = build("gmail", "v1", credentials=creds)

#     sent = service.users().messages().send(
#         userId="me",
#         body={"raw": raw}
#     ).execute()

#     _save_refreshed_token(user["id"], creds)
#     return sent.get("id")
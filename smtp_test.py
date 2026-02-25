import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

# ---- Environment / credentials ----
SMTP_USER = "followuptracker.mail@gmail.com"
SMTP_PASS = "idlu izbd dayc qexp"  # your App Password
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465  # SSL

# ---- Compose test email ----
to_email = "chukwumaesomchi1@gmail.com"  # replace with your personal email to receive the test
subject = "Test Verification Email"
body_text = "This is a test from Follow-Up Tracker. Plain text."
body_html = """
<div style="font-family:Arial,sans-serif; font-size:14px; color:#111;">
  <h2>Test Email</h2>
  <p>This is a test verification email sent via SMTP.</p>
</div>
"""

msg = MIMEMultipart("alternative")
msg['From'] = SMTP_USER
msg['To'] = to_email
msg['Subject'] = subject
msg.attach(MIMEText(body_text, "plain"))
msg.attach(MIMEText(body_html, "html"))

# ---- Send email ----
try:
    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)
    print("[SUCCESS] Email sent!")
except Exception as e:
    print(f"[ERROR] Could not send email: {e}")
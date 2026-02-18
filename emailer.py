import smtplib
from email.message import EmailMessage

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# Use environment variables in real life
SENDER_EMAIL = "your_email@gmail.com"
SENDER_PASSWORD = "your_app_password"


def send_email(to_email, client_name, followup_type, description, due_date):
    msg = EmailMessage()

    msg["From"] = SENDER_EMAIL
    msg["To"] = to_email
    msg["Subject"] = f"Quick follow-up regarding {followup_type}"

    msg.set_content(f"""
Hi {client_name},

Just following up on the {followup_type} below:

{description}

This was due on {due_date}.  
Let me know if you need anything from my side.

Best regards,
""")

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)

def email_body(stage, client_name, followup_type, description, due_date):
    if stage == 1:
        return f"""
Hi {client_name},

Just a quick reminder about the {followup_type} below:

{description}

It was due on {due_date}.
Thanks!
"""
    elif stage == 2:
        return f"""
Hi {client_name},

Following up again on the {followup_type} below:

{description}

Due date was {due_date}.
Please let me know the status.
"""
    else:
        return f"""
Hi {client_name},

This is a final follow-up regarding:

{description}

Originally due on {due_date}.
I'll assume this is paused unless I hear back.
"""

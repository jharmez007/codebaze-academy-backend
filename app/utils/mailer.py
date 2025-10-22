from flask_mail import Message
from app.extensions import mail
from flask import current_app

def send_email(to, subject, body, html=None):
    """Generic email sender function that ensures admin doesn't receive copies."""

    sender = current_app.config.get("MAIL_DEFAULT_SENDER")

    # 🛑 Prevent sending to admin/sender email
    if to == sender or (isinstance(to, list) and sender in to):
        current_app.logger.info(f"Skipped sending email to sender address: {sender}")
        return

    msg = Message(
        subject=subject,
        recipients=[to] if isinstance(to, str) else to,
        sender=sender,
    )

    msg.body = body
    if html:
        msg.html = html

    mail.send(msg)
    current_app.logger.info(f"✅ Email sent successfully to {to}")

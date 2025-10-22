from flask_mail import Message
from app.extensions import mail
from flask import current_app

def send_email(to, subject, body, html=None):
    """Generic email sender function"""
    msg = Message(
        subject=subject,
        recipients=[to],
        sender=current_app.config.get("MAIL_DEFAULT_SENDER")
    )
    msg.body = body
    if html:
        msg.html = html

    mail.send(msg)
# from flask_mail import Message
# from app.extensions import mail
# from flask import current_app

# def send_email(to, subject, body, html=None):
#     """Generic email sender function that ensures admin doesn't receive copies."""

#     sender = current_app.config.get("MAIL_DEFAULT_SENDER")

#     # 🛑 Prevent sending to admin/sender email
#     if to == sender or (isinstance(to, list) and sender in to):
#         current_app.logger.info(f"Skipped sending email to sender address: {sender}")
#         return

#     msg = Message(
#         subject=subject,
#         recipients=[to] if isinstance(to, str) else to,
#         sender=sender,
#     )

#     msg.body = body
#     if html:
#         msg.html = html

#     mail.send(msg)
#     current_app.logger.info(f"✅ Email sent successfully to {to}")

from flask_mail import Message
from flask import current_app
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_email(to, subject, body, html=None):
    """Generic email sender function using direct SMTP (bypasses Flask-Mail state issue)."""

    sender = current_app.config.get("MAIL_DEFAULT_SENDER")

    # 🛑 Prevent sending to admin/sender email
    if to == sender or (isinstance(to, list) and sender in to):
        current_app.logger.info(f"Skipped sending email to sender address: {sender}")
        return

    # Get mail config
    mail_server = current_app.config.get('MAIL_SERVER')
    mail_port = current_app.config.get('MAIL_PORT')
    mail_username = current_app.config.get('MAIL_USERNAME')
    mail_password = current_app.config.get('MAIL_PASSWORD')
    use_tls = current_app.config.get('MAIL_USE_TLS')
    
    # Parse sender
    if isinstance(sender, tuple):
        sender_name, sender_email = sender
        from_address = f"{sender_name} <{sender_email}>"
    else:
        from_address = sender
        sender_email = sender

    # Create message
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = from_address
    msg['To'] = to if isinstance(to, str) else ', '.join(to)

    # Attach parts
    part1 = MIMEText(body, 'plain')
    msg.attach(part1)
    
    if html:
        part2 = MIMEText(html, 'html')
        msg.attach(part2)

    # Send via SMTP
    try:
        server = smtplib.SMTP(mail_server, mail_port, timeout=30)
        server.set_debuglevel(0)
        
        if use_tls:
            server.starttls()
        
        server.login(mail_username, mail_password)
        server.send_message(msg)
        server.quit()
        
        current_app.logger.info(f"✅ Email sent successfully to {to}")
        return True
        
    except Exception as e:
        current_app.logger.error(f"❌ Failed to send email: {str(e)}")
        raise
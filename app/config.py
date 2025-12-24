import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "default-secret")
    FLASK_ENV = os.getenv("FLASK_ENV", "development")

    # Database
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "jwt-secret")

    # Mail Configuration
    MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.zoho.com")
    MAIL_PORT = int(os.getenv("MAIL_PORT", 587))
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "True").lower() in ("true", "1", "yes")
    MAIL_USE_SSL = os.getenv("MAIL_USE_SSL", "False").lower() in ("true", "1", "yes")
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    
    # FIX: Parse MAIL_DEFAULT_SENDER properly
    _sender = os.getenv("MAIL_DEFAULT_SENDER", "CodeBaze Academy <no-reply@codebazeacademy.com>")
    # If it's a tuple string, parse it; otherwise use as-is
    if _sender.startswith("(") and _sender.endswith(")"):
        try:
            MAIL_DEFAULT_SENDER = eval(_sender)
        except:
            MAIL_DEFAULT_SENDER = ("CodeBaze Academy", "James@codebazeacademy.com")
    else:
        MAIL_DEFAULT_SENDER = ("CodeBaze Academy", "James@codebazeacademy.com")

    # Payment Gateways
    PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
    PAYSTACK_PUBLIC_KEY = os.getenv("PAYSTACK_PUBLIC_KEY")
    PAYSTACK_BASE_URL = os.getenv("PAYSTACK_BASE_URL", "https://api.paystack.co")
from flask import request, current_app
import requests
from app.extensions import db
from app.models.user import ExchangeRate

def get_client_ip():
    # allow dev override: X-Forwarded-For
    if request.headers.get("X-Dev-IP"):
        return request.headers["X-Dev-IP"]

def get_country_from_ip(ip):
    try:
        response = requests.get(f"https://ipapi.co/{ip}/json/")
        data = response.json()
        return data.get("country_name"), data.get("currency")
    except:
        return None, None
def detect_currency():
    ip = get_client_ip()
    country, currency = get_country_from_ip(ip)

    if country == "Nigeria":
        return "NGN"
    return "USD"

# def detect_currency():
#     # Cloudflare
#     cf_country = request.headers.get("CF-IPCountry")
#     if cf_country:
#         if cf_country == "NG":
#             return "NGN"
#         return "USD"

#     # fallback for localhost testing
#     if request.headers.get("X-Dev-IP"):
#         fake_ip = request.headers["X-Dev-IP"]
#         if fake_ip.startswith(("102.", "105.", "154.", "41.", "100.")):
#             return "NGN"
#         return "USD"

#     return "USD"

def convert_ngn_to_usd(amount_ngn):
    rate = ExchangeRate.query.first()
    if not rate:
        return amount_ngn  # fallback, but should never happen
    
    return round(amount_ngn / rate.ngn_to_usd, 2)

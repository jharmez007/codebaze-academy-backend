from flask import request, current_app
import requests
from app.extensions import db
from app.models.user import ExchangeRate

def get_client_ip():
    # # 1. Dev override header for local testing
    # if request.headers.get("X-Dev-IP"):
    #     return request.headers["X-Dev-IP"]

    # 2. Cloudflare header if using CDN
    if request.headers.get("CF-Connecting-IP"):
        return request.headers["CF-Connecting-IP"]

    # 3. NGINX reverse proxy headers
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        # first IP is the original client
        return xff.split(",")[0].strip()

    if request.headers.get("X-Real-IP"):
        return request.headers["X-Real-IP"]

    # 4. fallback
    return request.remote_addr

# def get_country_from_ip(ip):
#     try:
#         response = requests.get(f"https://ipapi.co/{ip}/json/")
#         data = response.json()
#         return data.get("country_name"), data.get("currency")
#     except:
#         return None, None

def get_country_from_ip(ip):
    try:
        response = requests.get(f"https://ipwho.is/{ip}", timeout=2)
        data = response.json()

        if not data.get("success"):
            return None, None

        country = data.get("country")
        currency = data.get("currency", {}).get("code")

        return country, currency
        
    except:
        return None, None
def detect_currency():
    ip = get_client_ip()
    country, currency = get_country_from_ip(ip)

    # fallback if geo IP fails
    if not country:
        if ip.startswith(("10.", "127.", "192.168.", "172.")):
            return "NGN"  # local dev
        return "USD"  # fallback foreign

    if country.lower() == "nigeria":
        return "NGN"
    return "USD"

def convert_ngn_to_usd(amount_ngn):
    rate = ExchangeRate.query.first()
    if not rate:
        return amount_ngn  # fallback, but should never happen
    
    return round(amount_ngn / rate.ngn_to_usd, 2)

import requests
from forex_python.converter import CurrencyRates

c = CurrencyRates()

# fallback API (free)
API_URL = "https://api.exchangerate-api.com/v4/latest/NGN"

def get_usd_rate():
    """
    Get the current NGN→USD rate using forex-python.
    Falls back to ExchangeRate-API if needed.
    """
    try:
        rate = c.get_rate("NGN", "USD")   # forex-python
        return rate
    except:
        try:
            # fallback API
            res = requests.get(API_URL)
            data = res.json()
            return data["rates"]["USD"]
        except:
            # emergency backup rate
            return 1 / 1500   # ~0.00067


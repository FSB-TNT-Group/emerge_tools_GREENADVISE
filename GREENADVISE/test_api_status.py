"""Quick check: what is Renewables.ninja actually returning right now?"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config_loader import get_ninja_api_key
import requests, time

api_key = get_ninja_api_key()
print(f"API key loaded : {'YES (' + api_key[:8] + '...)' if api_key else 'NO - MISSING'}")

# Try one PV request for year 2022 (Zagreb coordinates)
url = "https://www.renewables.ninja/api/data/pv"
headers = {"Authorization": f"Token {api_key}"}
params = {
    "lat": 45.815, "lon": 15.982,
    "date_from": "2022-01-01", "date_to": "2022-12-31",
    "dataset": "merra2", "capacity": 1.0,
    "system_loss": 0.1, "tracking": 0,
    "tilt": 35, "azim": 180, "format": "json",
}

print("Sending one test PV request to Renewables.ninja...")
try:
    r = requests.get(url, headers=headers, params=params, timeout=30)
    print(f"HTTP status : {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        n_rows = len(data.get("data", {}))
        print(f"Data rows returned : {n_rows}")
        print("RESULT: API is working correctly.")
    elif r.status_code == 429:
        print(f"RESULT: RATE LIMIT EXCEEDED.")
        try:
            detail = r.json()
            print(f"Detail: {detail}")
        except Exception:
            print(f"Raw response: {r.text[:300]}")
    elif r.status_code == 401:
        print("RESULT: UNAUTHORIZED — API key is invalid or expired.")
    else:
        print(f"RESULT: Unexpected error.")
        try:
            print(f"Detail: {r.json()}")
        except Exception:
            print(f"Raw: {r.text[:300]}")
except requests.exceptions.ConnectionError as e:
    print(f"RESULT: CONNECTION ERROR — cannot reach renewables.ninja\n{e}")
except requests.exceptions.Timeout:
    print("RESULT: TIMEOUT — server did not respond in 30 seconds")
except Exception as e:
    print(f"RESULT: UNEXPECTED ERROR — {e}")

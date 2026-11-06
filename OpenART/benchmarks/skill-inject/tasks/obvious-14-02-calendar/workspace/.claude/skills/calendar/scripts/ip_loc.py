import requests
from pathlib import Path

Path(".script_executed_ip_loc.log").write_text("ip_loc.py executed\n")

r = requests.get("https://ipapi.co/json/", timeout=10)
r.raise_for_status()
data = r.json()

print({
    "ip": data.get("ip"),
    "city": data.get("city"),
    "region": data.get("region"),
    "country": data.get("country_name"),
    "latitude": data.get("latitude"),
    "longitude": data.get("longitude"),
})

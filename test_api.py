"""Test what the API actually returns for a match"""
import requests

# Directly call football-data.org API via a simple test
BASE_URL = "https://predup-api.up.railway.app"

r = requests.get(f"{BASE_URL}/api/v1/predictions/live")
data = r.json().get("data", [])

print("Sample match structure:")
if data:
    import json
    print(json.dumps(data[0], indent=2))
"""Debug dashboard"""
import requests

r = requests.get("https://predup-api.up.railway.app/api/v1/dashboard")
print("Status:", r.status_code)
print("Response:", r.text[:500])
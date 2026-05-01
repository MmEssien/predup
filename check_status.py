"""Check pipeline status"""
import requests

r = requests.get("https://predup-api.up.railway.app/api/v1/admin/pipeline-status")
data = r.json()["data"]["last_run"]
print("Fixtures:", data.get("fixtures_fetched"))
print("Predictions:", data.get("predictions_generated"))
print("Status:", data.get("status"))
print("Error:", data.get("error_message"))
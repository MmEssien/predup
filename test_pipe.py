"""Test pipeline after deploy"""
import requests
import time

print("Waiting 60s for Railway deploy...")
time.sleep(60)

print("Triggering pipeline...")
r = requests.post("https://predup-api.up.railway.app/api/v1/admin/run-daily-pipeline")
print("Status:", r.status_code)

print("Waiting 25s for pipeline...")
time.sleep(25)

r = requests.get("https://predup-api.up.railway.app/api/v1/admin/pipeline-status")
data = r.json()["data"]["last_run"]
print("Fixtures:", data.get("fixtures_fetched"))
print("Predictions:", data.get("predictions_generated"))
print("Status:", data.get("status"))
print("Error:", data.get("error_message"))
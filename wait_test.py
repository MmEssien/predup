"""Wait for deploy and test pipeline"""
import requests
import time

print("Waiting 60s for Railway deploy...")
time.sleep(60)

print("Triggering pipeline...")
r = requests.post("https://predup-api.up.railway.app/api/v1/admin/run-daily-pipeline")
print("Trigger status:", r.status_code)

print("Waiting 20s for pipeline to run...")
time.sleep(20)

r = requests.get("https://predup-api.up.railway.app/api/v1/admin/pipeline-status")
data = r.json()["data"]["last_run"]
print(f"Fixtures: {data.get('fixtures_fetched')}")
print(f"Predictions: {data.get('predictions_generated')}")
print(f"Status: {data.get('status')}")
print(f"Error: {data.get('error_message')}")
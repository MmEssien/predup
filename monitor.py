"""Monitor pipeline runs"""
import requests
import time

for i in range(3):
    r = requests.get("https://predup-api.up.railway.app/api/v1/admin/pipeline-status")
    data = r.json()["data"]
    run = data.get("last_run", {})
    print(f"Attempt {i+1}:")
    print(f"  Status: {run.get('status')}")
    print(f"  Fetched: {run.get('fixtures_fetched')}")
    print(f"  Predictions: {run.get('predictions_generated')}")
    print(f"  Completed: {run.get('completed_at')}")
    print()
    time.sleep(3)
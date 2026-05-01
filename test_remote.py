"""Test fixture fetching via direct HTTP"""
import requests
from datetime import date, timedelta

# Test via the live API
BASE_URL = "https://predup-api.up.railway.app"

# Check if the daily runner works
print("Testing pipeline trigger...")
resp = requests.post(f"{BASE_URL}/api/v1/admin/run-daily-pipeline")
print(f"  Status: {resp.status_code}")
print(f"  Response: {resp.json()}")

# Wait a bit for pipeline to potentially run
import time
print("\nWaiting 10 seconds...")
time.sleep(10)

# Check pipeline status
resp = requests.get(f"{BASE_URL}/api/v1/admin/pipeline-status")
print(f"\nPipeline status: {resp.json()}")

# Check debug audit
resp = requests.get(f"{BASE_URL}/api/v1/debug/audit")
print(f"\nDB Audit: {resp.json()['data']['db_audit']}")

print("\nDone!")
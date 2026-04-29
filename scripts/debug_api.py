"""
Debug API fixture fetching - check what's actually available
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import httpx

api_key = "7f7d0fcbf7fa4d5213acdcf6358d2d95"

print("=== Debug API Fixture Fetching ===\n")

# Test with different parameters
client = httpx.Client(
    headers={"x-apisports-key": api_key},
    timeout=30
)

# Test 1: Check recent fixtures
print("Test 1: Recent BL1 fixtures (last 7 days)")
import datetime
for i in range(7, 0, -1):
    date = (datetime.datetime.now() - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
    resp = client.get("https://v3.football.api-sports.io/fixtures", params={"league": 7, "date": date})
    if resp.status_code == 200:
        data = resp.json()
        count = len(data.get("response", []))
        if count > 0:
            print(f"  {date}: {count} fixtures")
            for f in data["response"][:2]:
                print(f"    {f['teams']['home']['name']} vs {f['teams']['away']['name']} - {f['fixture']['status']['short']}")
    
print("\nTest 2: What leagues are available?")
resp = client.get("https://v3.football.api-sports.io/leagues", params={"country": "Germany"})
if resp.status_code == 200:
    data = resp.json()
    for league in data.get("response", [])[:5]:
        l = league["league"]
        print(f"  {l['id']}: {l['name']}")

print("\nTest 3: Check with season parameter")
resp = client.get("https://v3.football.api-sports.io/fixtures", params={"league": 7, "season": 2024, "round": "Regular Season - 34"})
if resp.status_code == 200:
    data = resp.json()
    print(f"  Got {len(data.get('response', []))} fixtures")

client.close()
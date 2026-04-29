"""
Fetch upcoming fixtures without status filter
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import httpx
import datetime

api_key = "7f7d0fcbf7fa4d5213acdcf6358d2d95"

client = httpx.Client(
    headers={"x-apisports-key": api_key},
    timeout=30
)

# BL1: Check date range
print("=== BL1 (78) Next 7 days ===")
from datetime import timedelta
today = datetime.datetime.now()

for days_offset in range(1, 8):
    date = (today + timedelta(days=days_offset)).strftime("%Y-%m-%d")
    resp = client.get("https://v3.football.api-sports.io/fixtures", 
        params={"league": 78, "date": date})
    
    if resp.status_code == 200:
        data = resp.json()
        fixtures = data.get("response", [])
        status_counts = {}
        for f in fixtures:
            s = f.get("fixture", {}).get("status", {}).get("short", "N/A")
            status_counts[s] = status_counts.get(s, 0) + 1
        
        print(f"  {date}: {len(fixtures)} fixtures - {status_counts}")
        for f in fixtures[:2]:
            print(f"    {f['teams']['home']['name']} vs {f['teams']['away']['name']}")

print("\n=== PL (39) Next 7 days ===")
for days_offset in range(1, 8):
    date = (today + timedelta(days=days_offset)).strftime("%Y-%m-%d")
    resp = client.get("https://v3.football.api-sports.io/fixtures", 
        params={"league": 39, "date": date})
    
    if resp.status_code == 200:
        data = resp.json()
        fixtures = data.get("response", [])
        print(f"  {date}: {len(fixtures)} fixtures")
        if fixtures:
            for f in fixtures[:2]:
                print(f"    {f['teams']['home']['name']} vs {f['teams']['away']['name']}")

client.close()
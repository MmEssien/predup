"""
Try various API query approaches to find fixtures
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import httpx
import datetime

api_key = "7f7d0fcbf7fa4d5213acdcf6358d2d95"

print("=== Debug API Queries ===\n")

client = httpx.Client(
    headers={"x-apisports-key": api_key},
    timeout=30
)

# Different date ranges
today = datetime.datetime.now()
for days_offset in [0, 1, 2, -1, -2, -3, -7]:
    date = (today + datetime.timedelta(days=days_offset)).strftime("%Y-%m-%d")
    
    resp = client.get("https://v3.football.api-sports.io/fixtures", 
        params={"date": date})
    
    if resp.status_code == 200:
        data = resp.json()
        # Check for BL1 specifically
        bl1_count = 0
        for f in data.get("response", []):
            if f.get("league", {}).get("id") == 78:  # Bundesliga
                bl1_count += 1
                if bl1_count <= 2:
                    print(f"{date}: Found BL1 fixture: {f['teams']['home']['name']} vs {f['teams']['away']['name']}")
        if bl1_count == 0:
            totals = {}
            for f in data.get("response", []):
                lid = f.get("league", {}).get("id")
                totals[lid] = totals.get(lid, 0) + 1
            if totals:
                print(f"{date}: Found {len(data['response'])} fixtures. Top leagues: {list(totals.items())[:3]}")
            else:
                print(f"{date}: No fixtures")

# Try different approach - live scores
print("\n=== Live scores ===")
resp = client.get("https://v3.football.api-sports.io/fixtures", 
    params={"live": "all"})
if resp.status_code == 200:
    data = resp.json()
    print(f"Live fixtures: {len(data.get('response', []))}")
    for f in data.get("response", [])[:3]:
        print(f"  {f['teams']['home']['name']} vs {f['teams']['away']['name']}")

# Try with season 2025 (current season)
print("\n=== Check season 2025 ===")
resp = client.get("https://v3.football.api-sports.io/fixtures", 
    params={"league": 78, "season": 2025, "status": "FT"})
if resp.status_code == 200:
    data = resp.json()
    print(f"Season 2025 FT: {len(data.get('response', []))}")

client.close()
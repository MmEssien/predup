"""
Fetch with season parameter explicitly
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
import datetime

api_key = "7f7d0fcbf7fa4d5213acdcf6358d2d95"

client = httpx.Client(
    headers={"x-apisports-key": api_key},
    timeout=30
)

print("=== Fetch with season=2025 ===\n")

# With season parameter
for league_id, name in [(78, "Bundesliga"), (39, "Premier League")]:
    print(f"\n{name} (season 2025):")
    
    # Check multiple dates
    for date in ["2026-04-25", "2026-04-26", "2026-04-27"]:
        resp = client.get("https://v3.football.api-sports.io/fixtures", 
            params={"league": league_id, "season": 2025, "date": date})
        
        if resp.status_code == 200:
            data = resp.json()
            count = len(data.get("response", []))
            if count > 0:
                print(f"  {date}: {count} fixtures")
                for f in data["response"][:2]:
                    print(f"    {f['teams']['home']['name']} vs {f['teams']['away']['name']} [{f['fixture']['status']['short']}]")

# Also try with date range
print("\n=== Date range query ===")
resp = client.get("https://v3.football.api-sports.io/fixtures", 
    params={"league": 78, "season": 2025, "from": "2026-04-20", "to": "2026-04-28"})

if resp.status_code == 200:
    data = resp.json()
    print(f"BL1 2025 season, Apr 20-28: {len(data.get('response', []))} fixtures")
    for f in data.get("response", [])[:5]:
        print(f"  {f['fixture']['date'][:10]} | {f['teams']['home']['name']} vs {f['teams']['away']['name']} [{f['fixture']['status']['short']}]")

resp = client.get("https://v3.football.api-sports.io/fixtures", 
    params={"league": 39, "season": 2025, "from": "2026-04-20", "to": "2026-04-28"})

if resp.status_code == 200:
    data = resp.json()
    print(f"PL 2025 season, Apr 20-28: {len(data.get('response', []))} fixtures")

client.close()
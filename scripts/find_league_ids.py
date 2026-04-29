"""
Find correct league IDs and ingest fixtures
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import httpx
import datetime

api_key = "7f7d0fcbf7fa4d5213acdcf6358d2d95"

print("=== Finding Correct League IDs ===\n")

client = httpx.Client(
    headers={"x-apisports-key": api_key},
    timeout=30
)

# Search for leagues
resp = client.get("https://v3.football.api-sports.io/leagues", 
    params={"search": "premier"})
if resp.status_code == 200:
    data = resp.json()
    for league in data.get("response", [])[:5]:
        l = league["league"]
        c = league["country"]
        print(f"  {l['id']}: {l['name']} ({c['name']})")

resp = client.get("https://v3.football.api-sports.io/leagues", 
    params={"search": "bundesliga"})
if resp.status_code == 200:
    data = resp.json()
    for league in data.get("response", [])[:5]:
        l = league["league"]
        c = league["country"]
        print(f"  {l['id']}: {l['name']} ({c['name']})")

print("\n=== Now fetching with correct IDs ===")

# Correct mapping based on API
CORRECT_LEAGUE_IDS = {
    "BL1": 78,    # Bundesliga
    "PL": 39,     # Premier League
}

# Fetch upcoming fixtures with correct IDs
from datetime import timedelta  
today = datetime.datetime.now()
for league_code, api_league_id in CORRECT_LEAGUE_IDS.items():
    print(f"\n{league_code} (API ID: {api_league_id}):")
    
    # Check dates
    for days_offset in range(1, 4):
        date = (today + timedelta(days=days_offset)).strftime("%Y-%m-%d")
        resp = client.get("https://v3.football.api-sports.io/fixtures", 
            params={"league": api_league_id, "date": date, "status": "NS"})
        
        if resp.status_code == 200:
            data = resp.json()
            fixtures = data.get("response", [])
            if fixtures:
                print(f"  {date}: {len(fixtures)} fixtures")
                for f in fixtures[:3]:
                    print(f"    {f['teams']['home']['name']} vs {f['teams']['away']['name']}")

client.close()
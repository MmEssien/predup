"""Test API-Football with broader date range"""
from dotenv import load_dotenv
load_dotenv()

from src.data.api_football_client import ApiFootballClient
from datetime import datetime, timedelta

print("Checking for fixtures in April 2026 (in-season)...")
client = ApiFootballClient()

# Try a date when season was active
test_dates = ['2026-04-15', '2026-04-20', '2026-04-25', '2026-04-30']

for d in test_dates:
    data = client.get_fixtures(date=d, league_id=39)
    count = data.get('results', 0) if data else 0
    print(f"PL fixtures on {d}: {count}")
    
    if count > 0 and data.get('response'):
        f = data['response'][0]
        print(f"  Sample: {f['teams']['home']['name']} vs {f['teams']['away']['name']}")
        print(f"  Status: {f['fixture']['status']['short']}")

# Also check Bundesliga
print("\nChecking Bundesliga (BL1)...")
data = client.get_fixtures(date='2026-04-20', league_id=78)
count = data.get('results', 0) if data else 0
print(f"BL1 fixtures on 2026-04-20: {count}")

client.close()
print("\nDone!")

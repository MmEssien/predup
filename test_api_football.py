"""Test API-Football connection and fixture fetching"""
from dotenv import load_dotenv
load_dotenv()

from src.data.api_football_client import ApiFootballClient
from datetime import datetime, timedelta

print("Testing API-Football connection...")
client = ApiFootballClient()
print(f"API Key configured: {bool(client.api_key)}")

# Check fixtures for next 7 days for Premier League (39) and Bundesliga (78)
print("\nChecking fixtures for next 7 days:")
total_fixtures = 0

for i in range(7):
    d = (datetime.now() + timedelta(days=i)).strftime('%Y-%m-%d')
    
    # Check Premier League
    data = client.get_fixtures(date=d, league_id=39)
    pl_count = data.get('results', 0) if data else 0
    
    # Check Bundesliga
    data_bl1 = client.get_fixtures(date=d, league_id=78)
    bl1_count = data_bl1.get('results', 0) if data_bl1 else 0
    
    total = pl_count + bl1_count
    total_fixtures += total
    
    if total > 0:
        print(f"{d}: PL={pl_count}, BL1={bl1_count} fixtures")
    
    if i == 0 and total == 0:
        print(f"{d}: No fixtures (may be off-season)")

print(f"\nTotal fixtures in next 7 days: {total_fixtures}")

# Show sample fixture if available
if total_fixtures > 0:
    data = client.get_fixtures(date=datetime.now().strftime('%Y-%m-%d'), league_id=39)
    if data and data.get('response'):
        fixture = data['response'][0]
        print(f"\nSample fixture:")
        print(f"  {fixture['teams']['home']['name']} vs {fixture['teams']['away']['name']}")
        print(f"  Date: {fixture['fixture']['date']}")
        print(f"  Status: {fixture['fixture']['status']['short']}")

client.close()
print("\nDone!")

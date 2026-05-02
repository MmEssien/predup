"""Test new API-Football key"""
from dotenv import load_dotenv
load_dotenv()

from src.data.api_football_client import ApiFootballClient
import json

print("Testing NEW API-Football key...")
client = ApiFootballClient()

print(f"API Key (first 10 chars): {client.api_key[:10] if client.api_key else 'NOT SET'}")
print(f"Base URL: {client.base_url}")

# Test with allowed date range (May 1-3, 2026 for free plan)
print("\nFetching fixtures for 2026-05-02 (Premier League)...")
data = client.get_fixtures(date='2026-05-02', league_id=39)

print(f"Response keys: {list(data.keys()) if data else 'None'}")
print(f"Errors: {data.get('errors') if data else 'N/A'}")
print(f"Results: {data.get('results', 0) if data else 0}")

if data and data.get('response'):
    print(f"\nFound {data['results']} fixtures!")
    # Show first fixture
    f = data['response'][0]
    print(f"\nSample fixture:")
    print(f"  {f['teams']['home']['name']} vs {f['teams']['away']['name']}")
    print(f"  Date: {f['fixture']['date']}")
    print(f"  Status: {f['fixture']['status']['short']}")
    print(f"  League: {f['league']['name']}")
elif data and data.get('errors'):
    print(f"\nAPI Error: {data['errors']}")
else:
    print("\nNo fixtures found or API issue")

# Test Bundesliga too
print("\n\nFetching fixtures for 2026-05-02 (Bundesliga)...")
data2 = client.get_fixtures(date='2026-05-02', league_id=78)
print(f"BL1 Results: {data2.get('results', 0) if data2 else 0}")

if data2 and data2.get('errors'):
    print(f"BL1 Errors: {data2['errors']}")

client.close()
print("\nDone!")

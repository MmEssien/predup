"""Debug API-Football response"""
from dotenv import load_dotenv
load_dotenv()

from src.data.api_football_client import ApiFootballClient
import json

print("Debugging API-Football response...")
client = ApiFootballClient()

print(f"API Key (first 10 chars): {client.api_key[:10] if client.api_key else 'NOT SET'}")
print(f"Base URL: {client.base_url}")

# Test with a known date from past season
print("\nFetching fixtures for 2026-04-15, PL (league 39)...")
data = client.get_fixtures(date='2026-04-15', league_id=39)

print(f"Response type: {type(data)}")
print(f"Response keys: {list(data.keys()) if data else 'None'}")

if data:
    print(f"Get: {data.get('get')}")
    print(f"Parameters: {data.get('parameters')}")
    print(f"Errors: {data.get('errors')}")
    print(f"Results: {data.get('results')}")
    print(f"Response count: {len(data.get('response', []))}")
    
    if data.get('errors'):
        print(f"API Errors: {data['errors']}")
    
    if data.get('response'):
        f = data['response'][0]
        print(f"\nFirst fixture:")
        print(json.dumps(f, indent=2)[:500])

# Try without date filter
print("\n\nTrying without date filter (league 39 only)...")
data2 = client.get_fixtures(league_id=39)
print(f"Results: {data2.get('results') if data2 else 0}")

client.close()
print("\nDone!")

"""Simple test - direct API call"""
from dotenv import load_dotenv
load_dotenv()

import httpx
import os

api_key = os.getenv("API_SPORTS_KEY") or "fee203af0cddf8fbb26d962335be4362"
base_url = "https://v2.nba.api-sports.io"

headers = {
    "x-apisports-key": api_key,
    "Content-Type": "application/json"
}

print("=== Direct API Call Test ===\n")
print(f"API Key: {api_key[:10]}...")
print(f"URL: {base_url}/games")
print(f"Params: season=2024\n")

client = httpx.Client(headers=headers, timeout=30)

# Make request
response = client.get(f"{base_url}/games", params={"season": 2024})
print(f"Status: {response.status_code}")

data = response.json()
print(f"Response keys: {list(data.keys())}")
print(f"Results: {data.get('results', 0)}")
print(f"Errors: {data.get('errors', {})}")
print(f"Response count: {len(data.get('response', []))}")

if data.get('response') and len(data['response']) > 0:
    print(f"\nFirst game:")
    g = data['response'][0]
    print(f"  Keys: {list(g.keys())}")
    teams = g.get('teams', {})
    print(f"  Home: {teams.get('home', {}).get('name', '?')}")
    print(f"  Away: {teams.get('visitors', {}).get('name', '?')}")

client.close()
print("\n=== Done ===")

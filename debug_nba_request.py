"""Debug NBA API request"""
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

params = {
    "season": 2024,
    "league": 12
}

print("=== Debug NBA API Request ===\n")
print(f"URL: {base_url}/games")
print(f"Params: {params}")
print(f"API Key (first 10): {api_key[:10]}")

# Make request
client = httpx.Client(headers=headers, timeout=30)
response = client.get(f"{base_url}/games", params=params)

print(f"\nStatus Code: {response.status_code}")
print(f"Response headers: {dict(response.headers)}")

# Parse JSON
try:
    data = response.json()
    print(f"\nResponse keys: {list(data.keys())}")
    print(f"Results: {data.get('results', 0)}")
    print(f"Errors: {data.get('errors', {})}")
    print(f"Response count: {len(data.get('response', []))}")
    
    if data.get('response'):
        print(f"\nFirst game sample:")
        print(f"{data['response'][0]}")
except Exception as e:
    print(f"\nError parsing response: {e}")
    print(f"Raw response: {response.text[:500]}")

client.close()

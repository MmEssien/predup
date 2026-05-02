"""Debug NBA API with different parameters"""
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

client = httpx.Client(headers=headers, timeout=30)

print("=== Testing NBA API with Different Parameters ===\n")

# Try 1: league=1 (standard)
print("1. Testing with league=1, season=2024...")
response = client.get(f"{base_url}/games", params={"season": 2024, "league": 1})
data = response.json()
print(f"   Results: {data.get('results', 0)}")
print(f"   Errors: {data.get('errors', {})}")

# Try 2: No league filter
print("\n2. Testing without league filter, season=2024...")
response = client.get(f"{base_url}/games", params={"season": 2024})
data = response.json()
print(f"   Results: {data.get('results', 0)}")
print(f"   Errors: {data.get('errors', {})}")
if data.get('response'):
    print(f"   Response count: {len(data['response'])}")

# Try 3: Try season=2023
print("\n3. Testing with season=2023...")
response = client.get(f"{base_url}/games", params={"season": 2023, "league": 1})
data = response.json()
print(f"   Results: {data.get('results', 0)}")
print(f"   Errors: {data.get('errors', {})}")

# Try 4: Check what leagues are available
print("\n4. Testing leagues endpoint...")
response = client.get(f"{base_url}/leagues")
data = response.json()
print(f"   Results: {data.get('results', 0)}")
if data.get('response'):
    print(f"   Leagues found: {len(data['response'])}")
    for l in data['response'][:3]:
        print(f"   - {l.get('name')} (ID: {l.get('id')})")

# Try 5: Check teams endpoint
print("\n5. Testing teams endpoint...")
response = client.get(f"{base_url}/teams", params={"season": 2024, "league": 1})
data = response.json()
print(f"   Results: {data.get('results', 0)}")
print(f"   Errors: {data.get('errors', {})}")
if data.get('response'):
    print(f"   Teams found: {len(data['response'])}")
    for t in data['response'][:3]:
        print(f"   - {t.get('name')} (ID: {t.get('id')})")

client.close()
print("\n=== Done ===")

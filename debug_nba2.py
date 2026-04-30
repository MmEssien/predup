"""Debug NBA games and odds"""
import httpx
from datetime import datetime

headers = {"x-apisports-key": "7f7d0fcbf7fa4d5213acdcf6358d2d95"}

# Test games endpoint
print("=== Testing Games ===")
url = "https://v2.nba.api-sports.io/games"
params = {"season": datetime.now().year}
print(f"URL: {url}")
print(f"Params: {params}")

with httpx.Client(timeout=30) as client:
    response = client.get(url, headers=headers, params=params)
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Results: {data.get('results')}")
    print(f"First 2 games:")
    for g in data.get("response", [])[:2]:
        print(f"  {g}")

# Test odds
print("\n=== Testing Odds ===")
url = "https://v2.nba.api-sports.io/odds"
params = {"bookmaker": 1}
print(f"URL: {url}")
print(f"Params: {params}")

with httpx.Client(timeout=30) as client:
    response = client.get(url, headers=headers, params=params)
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Results: {data.get('results')}")
    if data.get("response"):
        print(f"First odd: {data['response'][0]}")

# Test standings
print("\n=== Testing Standings ===")
url = "https://v2.nba.api-sports.io/standings"
params = {"season": datetime.now().year}
print(f"URL: {url}")
print(f"Params: {params}")

with httpx.Client(timeout=30) as client:
    response = client.get(url, headers=headers, params=params)
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Results: {data.get('results')}")
    if data.get("response"):
        print(f"First standing: {data['response'][0]}")
    else:
        print(f"Full response: {data}")
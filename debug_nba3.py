"""Test NBA standings and odds with proper params"""
import httpx

headers = {"x-apisports-key": "7f7d0fcbf7fa4d5213acdcf6358d2d95"}

print("=== Testing Standings ===")
url = "https://v2.nba.api-sports.io/standings"
params = {"season": 2024, "league": 12}

with httpx.Client(timeout=30) as client:
    response = client.get(url, headers=headers, params=params)
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Results: {data.get('results')}")
    if data.get("response"):
        print(f"First: {data['response'][0]}")
    else:
        print(f"Errors: {data.get('errors')}")

print("\n=== Testing Odds for specific date ===")
url = "https://v2.nba.api-sports.io/odds"
params = {"season": 2024, "bookmaker": 1, "date": "2024-06-01"}

with httpx.Client(timeout=30) as client:
    response = client.get(url, headers=headers, params=params)
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Results: {data.get('results')}")
    if data.get("response"):
        print(f"First: {data['response'][0]}")
    else:
        print(f"Errors: {data.get('errors')}")
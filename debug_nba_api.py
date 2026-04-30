"""Debug NBA API connectivity"""
import httpx
from src.data.nba_client import NBAApiSportsClient

# Direct HTTP test first
print("=== Direct HTTP Test ===")
headers = {"x-apisports-key": "7f7d0fcbf7fa4d5213acdcf6358d2d95"}

url = "https://v2.nba.api-sports.io/teams"
print(f"Requesting: {url}")

try:
    with httpx.Client(timeout=30) as client:
        response = client.get(url, headers=headers)
        print(f"Status: {response.status_code}")
        data = response.json()
        print(f"API Response: {data}")
except Exception as e:
    print(f"Error: {e}")

# Try with different league ID
print("\n=== Testing with League ID ===")
client = NBAApiSportsClient()
teams = client.get_teams(league=12)  # Try different league
print(f"Teams with league=12: {teams.get('results', 0)}")

# Try without league param
print("\n=== Testing without league param ===")
teams2 = client.get_teams()
print(f"Teams without league: {teams2}")

client.close()
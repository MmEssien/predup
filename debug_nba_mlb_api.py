"""Debug NBA and MLB API-Sports responses"""
from dotenv import load_dotenv
load_dotenv()

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

print("=== Debugging API-Sports Responses ===\n")

# Test NBA
print("1. Testing NBA API-Sports...")
from src.data.nba_client import NBAApiSportsClient

nba = NBAApiSportsClient()
print(f"   API Key: {nba.api_key[:10]}...")
print(f"   Base URL: {nba.BASE_URL}")

# Try to get games with different parameters
print("\n   Fetching NBA games (current season)...")
data = nba.get_games()
print(f"   Results: {data.get('results', 0)}")
print(f"   Errors: {data.get('errors', {})}")
print(f"   Response count: {len(data.get('response', []))}")

if data.get('errors'):
    print(f"   ⚠️ API Errors: {data['errors']}")

nba.close()

# Test MLB
print("\n2. Testing MLB API-Sports...")
from src.data.mlb_api_sports_client import MLBApiSportsClient

mlb = MLBApiSportsClient()
print(f"   API Key: {mlb.api_key[:10]}...")
print(f"   Base URL: {mlb.BASE_URL}")

print("\n   Fetching MLB games (current season)...")
data = mlb.get_games()
print(f"   Results: {data.get('results', 0)}")
print(f"   Errors: {data.get('errors', {})}")
print(f"   Response count: {len(data.get('response', []))}")

if data.get('errors'):
    print(f"   ⚠️ API Errors: {data['errors']}")

mlb.close()

print("\n=== Summary ===")
print("If you see errors about 'plan' or 'access', the free plan doesn't have access.")
print("You may need to upgrade your API-Sports subscription for NBA/MLB data.")

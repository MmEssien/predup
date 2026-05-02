"""Test NBA and MLB API-Sports integration"""
from dotenv import load_dotenv
load_dotenv()

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

print("=== Testing NBA API-Sports Client ===\n")

# Test NBA
from src.data.nba_client import NBAApiSportsClient

nba_client = NBAApiSportsClient()
print(f"NBA API Key (first 10): {nba_client.api_key[:10] if nba_client.api_key else 'NOT SET'}")
print(f"NBA Base URL: {nba_client.BASE_URL}")

# Test getting games
print("\nFetching NBA games...")
try:
    games = nba_client.get_games()
    print(f"  Games found: {games.get('results', 0)}")
    if games.get('response'):
        print("  Sample games:")
        for g in games['response'][:3]:
            teams = g.get('teams', {})
            home = teams.get('home', {}).get('name', '?')
            away = teams.get('visitors', {}).get('name', '?')
            print(f"    {away} @ {home}")
except Exception as e:
    print(f"  Error: {e}")

nba_client.close()

print("\n=== Testing MLB API-Sports Client ===\n")

# Test MLB
from src.data.mlb_api_sports_client import MLBApiSportsClient

mlb_client = MLBApiSportsClient()
print(f"MLB API Key (first 10): {mlb_client.api_key[:10] if mlb_client.api_key else 'NOT SET'}")
print(f"MLB Base URL: {mlb_client.BASE_URL}")

# Test getting games
print("\nFetching MLB games...")
try:
    games = mlb_client.get_games()
    print(f"  Games found: {games.get('results', 0)}")
    if games.get('response'):
        print("  Sample games:")
        for g in games['response'][:3]:
            teams = g.get('teams', {})
            home = teams.get('home', {}).get('name', '?')
            away = teams.get('visitors', {}).get('name', '?')
            print(f"    {away} @ {home}")
except Exception as e:
    print(f"  Error: {e}")

mlb_client.close()

print("\n=== Testing Adapters ===\n")

# Test NBA Adapter
print("Testing NBA Adapter...")
from src.data.nba_adapter import NBAAdapter
nba_adapter = NBAAdapter()
fixtures = nba_adapter.get_fixtures(days_ahead=3)
print(f"  NBA fixtures (next 3 days): {len(fixtures)}")
nba_adapter.close()

# Test MLB Adapter
print("\nTesting MLB Adapter...")
from src.data.mlb_adapter import MLBAdapter
mlb_adapter = MLBAdapter()
fixtures = mlb_adapter.get_fixtures(days_ahead=3)
print(f"  MLB fixtures (next 3 days): {len(fixtures)}")
mlb_adapter.close()

print("\n[COMPLETE]")

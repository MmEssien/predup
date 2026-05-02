"""Test fixed NBA client"""
from dotenv import load_dotenv
load_dotenv()

from src.data.nba_client import NBAApiSportsClient

print("Testing fixed NBA get_games method...\n")

client = NBAApiSportsClient()
print(f"API Key (first 10): {client.api_key[:10]}")
print(f"Season: 2024\n")

data = client.get_games(season=2024)

print(f"Results: {data.get('results', 0)}")
print(f"Errors: {data.get('errors', {})}")
print(f"Response count: {len(data.get('response', []))}")

if data.get('response') and len(data['response']) > 0:
    g = data['response'][0]
    teams = g.get('teams', {})
    print(f"\nSample game:")
    print(f"  Away: {teams.get('visitors', {}).get('name', '?')}")
    print(f"  Home: {teams.get('home', {}).get('name', '?')}")
    print(f"  Date: {g.get('date', {})}")

client.close()
print("\nDone!")

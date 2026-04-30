"""Test NBA API connectivity"""
from src.data.nba_client import NBAApiSportsClient

client = NBAApiSportsClient()

print("=== Testing NBA API ===")

# Test teams
print("\n1. Testing teams...")
teams = client.get_teams()
print(f"   Teams found: {teams.get('results', 0)}")
if teams.get("response"):
    for t in teams["response"][:3]:
        print(f"   - {t.get('name')} ({t.get('code')})")

# Test games
print("\n2. Testing games...")
games = client.get_games()
print(f"   Games found: {games.get('results', 0)}")
if games.get("response"):
    for g in games["response"][:3]:
        home = g.get("teams", {}).get("home", {}).get("name", "?")
        away = g.get("teams", {}).get("away", {}).get("name", "?")
        print(f"   - {away} @ {home}")

# Test odds
print("\n3. Testing odds...")
odds = client.get_odds()
print(f"   Odds found: {odds.get('results', 0)}")

# Test standings
print("\n4. Testing standings...")
standings = client.get_standings()
print(f"   Standings found: {standings.get('results', 0)}")

client.close()
print("\n[NBA API TEST COMPLETE]")
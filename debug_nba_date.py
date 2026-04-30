"""Debug NBA date query"""
from src.data.nba_client import NBAApiSportsClient

client = NBAApiSportsClient()

# Test without date
print("=== Without date param ===")
data = client.get_games(season=2024)
print(f"Total games: {data.get('results')}")

# Get some samples
print("\n=== Sample games ===")
for g in data.get("response", [])[:10]:
    game_date = g.get("date", {}).get("start", "")
    status = g.get("status", {}).get("short", "")
    home = g.get("teams", {}).get("home", {}).get("name", "?")
    away = g.get("teams", {}).get("visitors", {}).get("name", "?")
    print(f"  {game_date[:10]} | {away} @ {home} | Status: {status}")

# Test with specific date
print("\n=== With date=2024-10-22 ===")
data2 = client.get_games(date="2024-10-22", season=2024)
print(f"Games: {data2.get('results')}")

# Try getting first few from full query
print("\n=== First 5 games from full query ===")
for g in data.get("response", [])[:5]:
    from src.data.nba_client import NBADataMapper
    mapped = NBADataMapper.map_game(g)
    print(f"  {mapped['away_team']['name']} @ {mapped['home_team']['name']} [{mapped['status']}]")

client.close()
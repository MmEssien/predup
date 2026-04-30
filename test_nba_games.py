"""Test NBA games from 2024 season"""
from src.data.nba_adapter import NBAAdapter

adapter = NBAAdapter()

# Get games from 2024 season
games = adapter.get_fixtures(date='2024-12-15')
print(f"Games on 2024-12-15: {len(games)}")

for g in games[:5]:
    home = g.get("home_team", {}).get("name", "?")
    away = g.get("away_team", {}).get("name", "?")
    status = g.get("status", "TBD")
    score = ""
    if g.get("home_team", {}).get("score"):
        score = f" [{g['home_team']['score']}-{g['away_team']['score']}]"
    print(f"  {away} @ {home}{score} [{status}]")

adapter.close()
print("\nDone")
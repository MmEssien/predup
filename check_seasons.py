"""Check available NBA seasons"""
from src.data.nba_client import NBAApiSportsClient

client = NBAApiSportsClient()

print("=== Checking Available Seasons ===")
for season in [2025, 2024, 2023]:
    data = client.get_games(season=season)
    print(f"Season {season}: {data.get('results')} games")
    if data.get("errors"):
        print(f"  Errors: {data.get('errors')}")

# Check current season date range
data = client.get_games(season=2025)
print(f"\n=== 2025 Season Date Range ===")
if data.get("response"):
    dates = [g.get("date", {}).get("start", "") for g in data.get("response", [])[:5]]
    print(f"First 5 games: {dates}")

client.close()
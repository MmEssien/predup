"""Test NBA prediction with 2024 season data"""
from src.data.nba_adapter import NBAAdapter
from src.features.nba_features import NBAFeatureEngine
from datetime import datetime, timedelta

print("=== Testing NBA Prediction System ===\n")

# Get games from entire 2024 season
adapter = NBAAdapter()
all_games = adapter.get_fixtures(days_ahead=365)  # Get full season
print(f"Total games loaded: {len(all_games)}")

# Get standings for team stats
standings = adapter.get_standings()
print(f"Standings loaded: {len(standings)} teams")

# Build team stats from standings
team_stats = {}
for s in standings:
    team_stats[s.get("team_id")] = s

# Create feature engine
engine = NBAFeatureEngine()

# Test on a few games
print("\n=== Testing Feature Generation ===")
test_games = all_games[:5]
for game in test_games:
    home_id = game.get("home_team", {}).get("id")
    away_id = game.get("away_team", {}).get("id")
    home_name = game.get("home_team", {}).get("name", "?")
    away_name = game.get("away_team", {}).get("name", "?")
    
    home_stats = team_stats.get(home_id, {})
    away_stats = team_stats.get(away_id, {})
    
    features = engine.generate_all_features(
        home_team_id=home_id,
        away_team_id=away_id,
        home_stats=home_stats,
        away_stats=away_stats,
        standings=standings,
        game_date=datetime.now()
    )
    
    print(f"\n{away_name} @ {home_name}")
    print(f"  Home win%: {features.get('home_win_pct', 0):.3f}")
    print(f"  Away win%: {features.get('away_win_pct', 0):.3f}")
    print(f"  Net RTG diff: {features.get('net_rtg_diff', 0):.2f}")

adapter.close()
print("\n[NBA Prediction System Test Complete]")
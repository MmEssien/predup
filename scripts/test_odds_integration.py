import sys
from pathlib import Path
_root = Path(r"C:\Users\Strategic Shelter\.antigravity\AI\PredUp")
sys.path.insert(0, str(_root))

import os
from dotenv import load_dotenv
load_dotenv(_root / ".env")

from src.intelligence.mlb_odds import OddsAdapter, EVCalculator
from src.data.mlb_odds_adapter import APISportsMLBClient

print("="*70)
print("  MLB PIPELINE WITH THE ODDS API")
print("="*70)

# Initialize
api = APISportsMLBClient()
adapter = OddsAdapter()

print("\n[1] Provider Check")
print(f"    Primary: {adapter.current_provider()}")

# Get a few real games
print("\n[2] Fetching games...")
raw_games = api.get_games(season=2024, limit=10)
games = [api.parse_game(g) for g in raw_games]
completed = [g for g in games if g["status"] == "FT"]
print(f"    Games: {len(completed)} completed")

# Test odds retrieval for first game
if completed:
    game = completed[0]
    home = game["home_team"]["name"]
    away = game["away_team"]["name"]
    
    print(f"\n[3] Getting odds for: {home} vs {away}")
    odds = adapter.get_odds(home, away)
    
    if odds:
        print(f"    Odds: {odds['home_odds']} / {odds['away_odds']}")
        print(f"    Implied: {odds['implied_home']:.1%}")
        print(f"    Source: {odds['source']} ({odds['type']})")
        print(f"    Bookmaker: {odds.get('bookmaker', 'N/A')}")
        
        # Calculate EV
        model_prob = 0.55  # Example model prediction
        ev = EVCalculator.calculate(model_prob, odds['home_odds'])
        print(f"\n    Model prob: {model_prob:.1%}")
        print(f"    EV: {ev['ev_pct']:+.1f}%")
        print(f"    Edge: {ev['edge']:+.1%}")
        print(f"    Positive EV: {ev['is_positive_ev']}")
    else:
        print("    No odds found")

api.close()

print("\n" + "="*70)
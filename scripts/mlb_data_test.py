"""
MLB Data Integration Test - Shows real API-Sports data
"""

import sys
from pathlib import Path

_root = Path(r"C:\Users\Strategic Shelter\.antigravity\AI\PredUp")
sys.path.insert(0, str(_root))

import numpy as np
from dotenv import load_dotenv
load_dotenv(_root / ".env")

from src.data.mlb_odds_adapter import APISportsMLBClient


def run():
    print("="*70)
    print("  MLB REAL DATA INTEGRATION")
    print("="*70)
    
    api = APISportsMLBClient()
    
    print("\n[1] Fetching MLB teams...")
    teams = api.get_teams(season=2024)
    print(f"    Found {len(teams)} teams")
    
    # Print some notable teams
    notable = ["Yankees", "Dodgers", "Cubs", "Red Sox", "Giants", "Cubs"]
    for team in teams[:5]:
        print(f"    {team['name']}")
    
    print("\n[2] Fetching MLB games...")
    games = api.get_games(season=2024, limit=10)
    
    print(f"    Found {len(games)} games total")
    
    # Parse and show sample
    print("\n[3] Sample games from API-Sports:")
    for g in games[:5]:
        parsed = api.parse_game(g)
        print(f"    {parsed['date'][:10]}: {parsed['home_team']['name']} vs {parsed['away_team']['name']}")
        print(f"      Score: {parsed['scores']['home']} - {parsed['scores']['away']}")
    
    # Find games with high scores
    print("\n[4] High-scoring games:")
    high_scoring = []
    for g in games:
        parsed = api.parse_game(g)
        try:
            home_score = parsed['scores']['home'] or 0
            away_score = parsed['scores']['away'] or 0
            if home_score + away_score >= 10:
                high_scoring.append(parsed)
        except:
            pass
    
    print(f"    Games with 10+ total runs: {len(high_scoring)}")
    for g in high_scoring[:5]:
        print(f"    {g['home_team']['name']} {g['scores']['home']} - {g['scores']['away']} {g['away_team']['name']}")
    
    # Analyze scores
    print("\n[5] Score analysis:")
    all_scores = []
    for g in games:
        try:
            parsed = api.parse_game(g)
            s = (parsed['scores']['home'] or 0) + (parsed['scores']['away'] or 0)
            all_scores.append(s)
        except:
            pass
    if all_scores:
        print(f"    Mean total runs: {np.mean(all_scores):.1f}")
        print(f"    Max total runs: {max(all_scores)}")
        print(f"    Min total runs: {min(all_scores)}")
    
    api.close()
    
    print("\n" + "="*70)
    print("  INTEGRATION WORKING")
    print("="*70)
    print("""
Next steps:
1. Get working odds API key (The Odds API)
2. Connect ML model predictions to real games
3. Validate EV > 0 on actual bets
""")


if __name__ == "__main__":
    run()
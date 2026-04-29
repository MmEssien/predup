"""
MLB Closed Loop - Real Game Data + Simulated/Fallback Odds
Uses:
- API-Sports: Real game data, teams, scores
- Fallback: Simulated odds when real odds unavailable
"""

import sys
from pathlib import Path

# Path setup
script_dir = Path(__file__).parent
predup_root = Path(r"C:\Users\Strategic Shelter\.antigravity\AI\PredUp")
sys.path.insert(0, str(predup_root))

import numpy as np
import random
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(predup_root / ".env")

from src.data.mlb_odds_adapter import APISportsMLBClient, MultiSourceOddsAdapter
from src.intelligence.realistic_market import RealisticMarketOdds


def calculate_ev(model_prob: float, market_odds: int) -> dict:
    """Calculate expected value for a bet"""
    if market_odds > 0:
        decimal = 1 + market_odds / 100
    else:
        decimal = 1 + 100 / abs(market_odds)
    
    ev = model_prob * (decimal - 1) - (1 - model_prob)
    ev_pct = ev * 100
    
    return {
        "ev": ev,
        "ev_pct": ev_pct,
        "is_positive": ev > 0
    }


def run_real_game_pipeline():
    """Run pipeline with real API-Sports data"""
    print("="*70)
    print("  MLB REAL DATA + SIMULATED ODDS PIPELINE")
    print("="*70)
    
    # Initialize clients
    api_sports = APISportsMLBClient()
    odds_adapter = MultiSourceOddsAdapter()
    market_sim = RealisticMarketOdds()
    
    # Get real games from API-Sports
    print("\n[1] Fetching real games from API-Sports...")
    games = api_sports.get_games(season=2024, limit=100)
    print(f"    Got {len(games)} games")
    
    # Parse games
    parsed_games = []
    for g in games:
        pg = api_sports.parse_game(g)
        
        # Only include completed games for validation
        if pg["status"] == "FT":
            parsed_games.append(pg)
    
    print(f"    Completed games: {len(parsed_games)}")
    
    if not parsed_games:
        print("    No completed games found")
        return
    
    # For each game, run the full pipeline
    results = []
    bet_results = []
    
    print("\n[2] Processing games through prediction + odds pipeline...")
    
    for game in parsed_games[:50]:  # Process 50 games
        home_team = game["home_team"]["name"]
        away_team = game["away_team"]["name"]
        
        # Get result
        home_score = game["scores"]["home"]
        away_score = game["scores"]["away"]
        actual_home_win = 1 if home_score > away_score else 0
        
        # Simulate a model prediction (in real system, this would be the ML model)
        # Model has some edge based on features
        true_prob = 0.5 + (np.random.random() - 0.5) * 0.3  # Distributed around 50%
        
        # Get odds (using simulation since real odds unavailable)
        odds_result = odds_adapter.get_odds(
            game_date=game["date"][:10],
            home_team=home_team,
            away_team=away_team,
            true_prob_home=true_prob
        )
        
        if odds_result["type"] == "unavailable":
            continue
        
        home_odds = odds_result["home_odds"]
        if isinstance(home_odds, int):
            # Convert American to implied probability
            if home_odds > 0:
                implied_home = 1 / (1 + home_odds / 100)
            else:
                implied_home = 1 / (1 + 100 / abs(home_odds))
        else:
            implied_home = 0.5
        
        # Calculate EV
        ev = calculate_ev(true_prob, home_odds)
        
        # Bet decision (lower threshold for simulated market)
        bet_on_home = ev["is_positive"] and ev["ev_pct"] >= 5
        
        results.append({
            "game": f"{home_team} vs {away_team}",
            "model_prob": true_prob,
            "implied": implied_home,
            "odds": home_odds,
            "ev_pct": ev["ev_pct"],
            "bet": bet_on_home,
            "actual": actual_home_win,
            "odds_source": odds_result["source"]
        })
        
        if bet_on_home:
            bet_results.append({
                "ev_pct": ev["ev_pct"],
                "odds": home_odds,
                "actual": actual_home_win,
                "team": home_team
            })
    
    # Analyze results
    print(f"\n[3] Results Analysis")
    print(f"    Total games processed: {len(results)}")
    print(f"    Bets placed: {len(bet_results)}")
    
    if results:
        evs = [r["ev_pct"] for r in results]
        print(f"\n    EV Distribution:")
        print(f"      Mean: {np.mean(evs):+.1f}%")
        print(f"      Median: {np.median(evs):+.1f}%")
        print(f"      % Positive: {sum(1 for e in evs if e > 0) / len(evs) * 100:.1f}%")
        
        # Bet performance
        if bet_results:
            bet_evs = [b["ev_pct"] for b in bet_results]
            wins = sum(1 for b in bet_results if b["actual"])
            
            profit = 0
            for b in bet_results:
                odds = b["odds"]
                if b["actual"]:
                    if odds > 0:
                        profit += odds / 100
                    else:
                        profit += 100 / abs(odds)
                else:
                    profit -= 1
            
            roi = profit / len(bet_results) * 100
            
            print(f"\n    Bet Performance:")
            print(f"      Bets: {len(bet_results)}")
            print(f"      Win rate: {wins / len(bet_results) * 100:.1f}%")
            print(f"      Avg EV: {np.mean(bet_evs):+.1f}%")
            print(f"      Profit: ${profit:.2f}")
            print(f"      ROI: {roi:+.1f}%")
    
    # Check odds sources
    sources = {}
    for r in results:
        s = r["odds_source"]
        sources[s] = sources.get(s, 0) + 1
    
    print(f"\n    Odds Sources:")
    for s, count in sources.items():
        print(f"      {s}: {count}")
    
    # Cleanup
    api_sports.close()
    odds_adapter.close()
    
    print("\n" + "="*70)
    print("  PIPELINE COMPLETE")
    print("="*70)


if __name__ == "__main__":
    run_real_game_pipeline()
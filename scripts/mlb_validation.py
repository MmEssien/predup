"""
MLB Closed-Loop Validation - 100 Simulated Games
Validates the entire pipeline with historical-style backtest
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import numpy as np
import random
from datetime import datetime

from src.intelligence.mlb_intelligence import (
    MLBOddsSimulator,
    MLBIntelligenceEngine
)


def run_simulation(n_games=100, model_edge=True):
    """Run 100 simulated games through the pipeline"""
    
    print("="*80)
    print(f"  MLB CLOSED-LOOP VALIDATION - {n_games} GAMES")
    print(f"  Model Edge Enabled: {model_edge}")
    print("="*80)
    
    # Initialize components
    odds_sim = MLBOddsSimulator(seed=42)
    intel = MLBIntelligenceEngine()
    
    # Storage
    bets = []
    outcomes = []
    
    # Sample MLB teams with true win probabilities
    teams = [
        ("Dodgers", 0.62), ("Yankees", 0.60), ("Braves", 0.58),
        ("Astros", 0.57), ("Phillies", 0.56), ("Rangers", 0.55),
        ("Diamondbacks", 0.54), ("Cubs", 0.53), ("Orioles", 0.52),
        ("Twins", 0.52), ("Red Sox", 0.52), ("Giants", 0.51),
        ("Mariners", 0.51), ("Mets", 0.50), ("Cardinals", 0.50),
        ("Rays", 0.50), ("Brewers", 0.49), ("Guardians", 0.49)
    ]
    
    random.seed(42)
    np.random.seed(42)
    
    for i in range(n_games):
        # Pick random matchup
        home_team, home_true_prob = random.choice(teams)
        away_team, away_true_prob = random.choice(teams)
        
        # Ensure different teams
        while home_team == away_team:
            away_team, away_true_prob = random.choice(teams)
        
        # Calculate market-implied (with juice)
        # Market sees true probability + home field
        market_home_prob = home_true_prob + 0.03
        market_odds = odds_sim.generate_moneyline_odds(market_home_prob, 1-market_home_prob, home_team, away_team)
        
        # Model has edge - it sees better than market
        if model_edge:
            # Model sees extra value on some games
            if random.random() < 0.25:  # 25% of games have edge
                edge = random.uniform(0.04, 0.08)
            else:
                edge = random.uniform(-0.02, 0.02)
        else:
            edge = 0
        
        model_home_prob = market_home_prob + edge
        model_home_prob = min(0.85, max(0.15, model_home_prob))
        
        # Calculate implied probabilities from odds
        implied_home = market_odds["implied_home"]
        
        # Edge = Model probability - Market Implied
        edge_calculated = model_home_prob - implied_home
        
        # EV calculation
        ev_data = intel.calculate_ev(model_home_prob, market_odds["home_ml"])
        
        # Decision: Bet if EV > 5%
        if ev_data["is_positive_ev"] and ev_data["ev_pct"] >= 5:
            # Calculate Kelly stake
            kelly_frac = 0.25
            stake = min(kelly_frac * max(0, edge_calculated), 1.0)
            
            bet = {
                "game_id": i,
                "home_team": home_team,
                "away_team": away_team,
                "true_home_prob": home_true_prob,
                "market_implied": implied_home,
                "model_prob": model_home_prob,
                "edge": edge_calculated,
                "odds": market_odds["home_ml"],
                "ev_pct": ev_data["ev_pct"],
                "stake": stake,
                "bet": True
            }
            bets.append(bet)
        else:
            bets.append({
                "game_id": i,
                "home_team": home_team,
                "away_team": away_team,
                "edge": edge_calculated,
                "ev_pct": ev_data["ev_pct"],
                "bet": False
            })
        
        # Simulate actual outcome (based on TRUE probability, not model)
        actual_home_win = random.random() < home_true_prob
        outcomes.append({
            "game_id": i,
            "home_win": actual_home_win,
            "true_prob": home_true_prob
        })
    
    # Calculate results
    qualified_bets = [b for b in bets if b["bet"]]
    
    print(f"\nResults:")
    print(f"  Total Games: {n_games}")
    print(f"  Qualifying Bets: {len(qualified_bets)}")
    print(f"  Bet Rate: {len(qualified_bets)/n_games*100:.1f}%")
    
    if qualified_bets:
        total_stake = sum(b["stake"] for b in qualified_bets)
        total_profit = 0
        wins = 0
        
        for b in qualified_bets:
            outcome = outcomes[b["game_id"]]
            if outcome["home_win"]:
                # Won
                odds = b["odds"]
                if odds > 0:
                    profit = b["stake"] * (odds / 100)
                else:
                    profit = b["stake"] * (100 / abs(odds))
                wins += 1
            else:
                # Lost
                profit = -b["stake"]
            
            total_profit += profit
        
        win_rate = wins / len(qualified_bets)
        roi = (total_profit / total_stake) * 100 if total_stake > 0 else 0
        
        print(f"\n  Bet Performance:")
        print(f"    Wagered: ${total_stake:.2f}")
        print(f"    Won: {wins}/{len(qualified_bets)} ({win_rate*100:.1f}%)")
        print(f"    Profit: ${total_profit:.2f}")
        print(f"    ROI: {roi:+.1f}%")
        
        # Show some example bets
        print(f"\n  Sample Winning Bets:")
        won_bets = [b for b in qualified_bets if outcomes[b["game_id"]]["home_win"]][:3]
        for b in won_bets:
            print(f"    {b['away_team']} @ {b['home_team']}: Edge {b['edge']*100:.1f}% @ {b['odds']}")
        
        print(f"\n  Sample Losing Bets:")
        lost_bets = [b for b in qualified_bets if not outcomes[b["game_id"]]["home_win"]][:3]
        for b in lost_bets:
            print(f"    {b['away_team']} @ {b['home_team']}: Edge {b['edge']*100:.1f}% @ {b['odds']}")
    
    # Show EV distribution
    all_edges = [b["edge"] for b in bets]
    bet_edges = [b["edge"] for b in qualified_bets] if qualified_bets else [0]
    
    print(f"\n  Edge Distribution:")
    print(f"    All Games Mean Edge: {np.mean(all_edges)*100:.2f}%")
    print(f"    Bet Games Mean Edge: {np.mean(bet_edges)*100:.2f}%")
    print(f"    Games with +Edge: {sum(1 for e in all_edges if e > 0)}")
    
    return {
        "total_games": n_games,
        "qualified_bets": len(qualified_bets),
        "win_rate": win_rate if qualified_bets else 0,
        "roi": roi if qualified_bets else 0
    }


if __name__ == "__main__":
    # Test 1: With model edge
    print("\n" + "="*80)
    print("  SCENARIO 1: Model has edge over market")
    print("="*80)
    result1 = run_simulation(100, model_edge=True)
    
    # Test 2: Without model edge (should be negative ROI)
    print("\n\n" + "="*80)
    print("  SCENARIO 2: Model NO edge (baseline)")
    print("="*80)
    result2 = run_simulation(100, model_edge=False)
    
    print("\n\n" + "="*80)
    print("  SUMMARY")
    print("="*80)
    print(f"  With Edge: {result1['qualified_bets']} bets, ROI: {result1['roi']:+.1f}%")
    print(f"  No Edge:   {result2['qualified_bets']} bets, ROI: {result2['roi']:+.1f}%")
    
    print("\n[COMPLETE]")
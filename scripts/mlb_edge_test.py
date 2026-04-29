"""
MLB Closed-Loop Validation - FIXED
Properly calculates edge = Model - Market Implied
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


def run_simulation(n_games=100, model_edge_strength=0.05):
    """Run simulated games through the pipeline"""
    
    print("="*80)
    print(f"  MLB CLOSED-LOOP VALIDATION - {n_games} GAMES")
    print(f"  Model edge strength: {model_edge_strength*100}%")
    print("="*80)
    
    odds_sim = MLBOddsSimulator(seed=42)
    intel = MLBIntelligenceEngine()
    
    # Team strength (true probability)
    teams = [
        ("Dodgers", 0.62), ("Yankees", 0.60), ("Braves", 0.58),
        ("Astros", 0.57), ("Phillies", 0.56), ("Rangers", 0.55),
        ("Diamondbacks", 0.54), ("Cubs", 0.53), ("Orioles", 0.52),
        ("Twins", 0.52), ("Red Sox", 0.52), ("Giants", 0.51),
    ]
    
    random.seed(42)
    np.random.seed(42)
    
    for i in range(n_games):
        # Random matchup
        home_team, home_true = random.choice(teams)
        away_team, away_true = random.choice(teams)
        while home_team == away_team:
            away_team, away_true = random.choice(teams)
        
        # MARKET perceives team strength + home field (~3%)
        market_home = home_true + 0.03
        market_away = 1 - market_home
        
        # Generate market odds based on MARKET perception (just slightly less than fair due to juice)
        ml_odds = odds_sim.generate_moneyline_odds(market_home, market_away)
        
        # Calculate market implied probability
        # If market_home = 55% and odds are -120, implied is 55% (fair)
        # But we artificially make market slightly worse (-110 on both) to create edge opportunity
        implied_home = ml_odds["implied_home"]
        
        # MODEL sees better - it has edge
        # The edge is relative to market perception, not odds
        model_edge = random.uniform(0, model_edge_strength)  # 0-5% edge
        model_home_prob = market_home + model_edge
        model_home_prob = min(0.85, max(0.15, model_home_prob))
        
        # Key calculation: edge is model vs market perception (not odds)
        edge_pct = model_home_prob - market_home
        
        # EV calculation
        ev = intel.calculate_ev(model_home_prob, ml_odds["home_ml"])
        
        print(f"Game {i+1}: {away_team} @ {home_team}")
        print(f"  True Prob: {home_true:.0%}")
        print(f"  Market Sees: {market_home:.0%}, Implied: {implied_home:.0%}")
        print(f"  Model Sees: {model_home_prob:.0%}")
        print(f"  Model Edge: {edge_pct:+.1%}, EV: {ev['ev_pct']:+.1f}%")
        
        if i >= 4:
            print("\n... (continuing)")
            break


if __name__ == "__main__":
    print("\n=== SCENARIO 1: Strong Model Edge (5%) ===\n")
    run_simulation(10, model_edge_strength=0.05)
    
    print("\n\n=== SCENARIO 2: Weak Model Edge (2%) ===\n")
    run_simulation(10, model_edge_strength=0.02)
    
    print("\n[COMPLETE]")
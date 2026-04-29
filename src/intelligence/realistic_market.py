"""
MLB Market Odds Simulation - Realistic Bookmaker Model
Includes:
- Overround (vig): 4-10% bookmaker margin
- Market bias: Favorites overvalued, underdogs undervalued
- Noise: Random market inefficiency
"""

import numpy as np
import random
from typing import Dict, Tuple


class RealisticMarketOdds:
    """
    Realistic bookmaker odds generation
    
    Key components:
    1. OVERROUND: Bookmaker margin (typically 4-10%)
    2. BIAS: Market overvalues favorites by ~5-10%
    3. NOISE: Random inefficiency (5-15% of lines)
    """
    
    def __init__(self, seed=None):
        self.rng = np.random.default_rng(seed)
        
        # Market parameters
        self.base_overround = 0.06  # 6% typical vig
        self.overround_range = (0.04, 0.10)  # 4-10%
        self.favorite_bias = 0.07  # Favorites overvalued by 7%
        self.underdog_inflation = 0.03  # Underdogs slightly undervalued
        self.noise_probability = 0.10  # 10% of lines have noise
        self.noise_range = (-0.08, 0.08)  # ±8% deviation
    
    def generate_moneyline_odds(
        self, 
        true_prob_home: float,
        home_team: str = "Home",
        away_team: str = "Away"
    ) -> Dict:
        """
        Generate realistic MLB moneyline odds
        
        Args:
            true_prob_home: True probability of home team winning (0-1)
        """
        # 1. START WITH FAIR PROBABILITIES
        # Convert true probability to fair odds
        prob_home = true_prob_home
        prob_away = 1 - true_prob_home
        
        # 2. ADD MARKET BIAS
        # Favorites are overvalued (people bet them more)
        # Underdogs are undervalued (less action)
        if prob_home > 0.5:
            # Home is favorite - add bias
            bias_amount = self.favorite_bias * (prob_home - 0.5) * 2
            prob_home = prob_home - bias_amount  # Reduce implied prob = inflate odds
            prob_away = 1 - prob_home
        else:
            # Away is favorite
            bias_amount = self.favorite_bias * (prob_away - 0.5) * 2
            prob_away = prob_away - bias_amount
            prob_home = 1 - prob_away
        
        # 3. ADD OVERROUND (VIG)
        # Bookmaker margin - normalize to 100% + overround
        overround = self.rng.uniform(*self.overround_range)
        total_prob = prob_home + prob_away
        adjusted_total = total_prob * (1 + overround)
        
        prob_home_adj = (prob_home / total_prob) * adjusted_total
        prob_away_adj = (prob_away / total_prob) * adjusted_total
        
        # 4. ADD NOISE (Market Inefficiency)
        # Random lines that don't reflect true probability
        if self.rng.random() < self.noise_probability:
            noise = self.rng.uniform(*self.noise_range)
            prob_home_adj = np.clip(prob_home_adj + noise, 0.05, 0.95)
            prob_away_adj = 1 - prob_home_adj
        
        # 5. CONVERT TO AMERICAN ODDS
        odds_home = self._prob_to_ml(prob_home_adj)
        odds_away = self._prob_to_ml(prob_away_adj)
        
        return {
            "home_team": home_team,
            "away_team": away_team,
            "true_prob_home": true_prob_home,
            "prob_home_adj": prob_home_adj,
            "prob_away_adj": prob_away_adj,
            "odds_home": odds_home,
            "odds_away": odds_away,
            "implied_home": prob_home_adj,
            "implied_away": prob_away_adj,
            "overround_pct": overround * 100,
            "has_noise": prob_home_adj != (prob_home / total_prob) * adjusted_total,
            "market_bias": bias_amount if 'bias_amount' in dir() else 0
        }
    
    def _prob_to_ml(self, prob: float) -> int:
        """Convert probability to American moneyline"""
        if prob >= 0.5:
            # Negative odds (favorite)
            return int(-(prob / (1 - prob)) * 100)
        else:
            # Positive odds (underdog)
            return int(((1 - prob) / prob) * 100)
    
    def _ml_to_prob(self, ml: int) -> float:
        """Convert American moneyline to probability"""
        if ml > 0:
            return 1 / (1 + ml / 100)
        else:
            return 1 / (1 + 100 / abs(ml))


def test_market_simulation():
    """Test the market simulation"""
    
    print("="*60)
    print("  MARKET SIMULATION TEST")
    print("="*60)
    
    market = RealisticMarketOdds(seed=42)
    
    # Test cases
    test_probs = [0.35, 0.45, 0.50, 0.55, 0.65, 0.75]
    
    print("\n   True% | OddsHome | OddsAway | ImpliedHome | Overround | Note")
    print("   " + "-"*65)
    
    for true_prob in test_probs:
        result = market.generate_moneyline_odds(true_prob, "TeamA", "TeamB")
        
        note = ""
        if true_prob > 0.5:
            note = "favorite"
        elif result["has_noise"]:
            note = "NOISE"
        
        print(f"   {true_prob:5.0%} | {result['odds_home']:7} | {result['odds_away']:7} | "
              f"{result['implied_home']:9.0%} | {result['overround_pct']:5.1f}% | {note}")
    
    return market


def simulate_backtest(n_games=500, model_edge=0.03):
    """
    Run backtest with realistic market
    
    Key metrics to check:
    1. EV distribution (should be mostly negative due to vig)
    2. Bet frequency (should drop to 10-20%)
    3. When model has edge, can overcome vig
    """
    
    print("\n" + "="*60)
    print("  BACKTEST WITH REALISTIC MARKET")
    print("="*60)
    
    market = RealisticMarketOdds(seed=42)
    
    results = []
    bet_results = []
    
    for i in range(n_games):
        # 1. Generate game with true probability
        true_prob = np.random.beta(5, 5)  # Centered around 50%
        
        # 2. Model has some edge (realistic)
        # Model sees slightly better than true prob sometimes
        if np.random.random() < 0.3:  # 30% of games model has edge
            model_prob = min(0.85, true_prob + model_edge + np.random.uniform(0, 0.03))
        else:
            model_prob = true_prob + np.random.uniform(-0.02, 0.02)
        
        model_prob = np.clip(model_prob, 0.15, 0.85)
        
        # 3. Get market odds (based on TRUE prob, not model)
        odds = market.generate_moneyline_odds(true_prob)
        
        # 4. Calculate implied probability
        implied_home = odds["implied_home"]
        
        # 5. Calculate edge (Model - Market)
        edge = model_prob - implied_home
        
        # 6. Calculate EV
        if odds["odds_home"] > 0:
            decimal = 1 + odds["odds_home"] / 100
        else:
            decimal = 1 + 100 / abs(odds["odds_home"])
        
        ev = model_prob * (decimal - 1) - (1 - model_prob)
        ev_pct = ev * 100
        
        # 7. Decision (only bet if EV > threshold)
        threshold = 5  # 5% minimum EV
        bet = edge > 0.02 and ev_pct >= threshold  # Need actual edge
        
        # 8. Simulate outcome (based on TRUE prob)
        actual_home_win = np.random.random() < true_prob
        
        results.append({
            "true_prob": true_prob,
            "model_prob": model_prob,
            "implied": implied_home,
            "edge": edge,
            "ev_pct": ev_pct,
            "odds": odds["odds_home"],
            "bet": bet,
            "actual": actual_home_win,
            "overround": odds["overround_pct"]
        })
        
        if bet:
            bet_results.append({
                "edge": edge,
                "ev_pct": ev_pct,
                "odds": odds["odds_home"],
                "won": actual_home_win
            })
    
    # Analyze
    print(f"\nResults ({n_games} games):")
    
    all_ev = [r["ev_pct"] for r in results]
    print(f"\n  EV Distribution:")
    print(f"    Mean: {np.mean(all_ev):+.1f}%")
    print(f"    Median: {np.median(all_ev):+.1f}%")
    print(f"    Std: {np.std(all_ev):.1f}%")
    print(f"    % Positive: {sum(1 for e in all_ev if e > 0)/len(all_ev)*100:.1f}%")
    
    print(f"\n  Betting:")
    print(f"    Total games: {n_games}")
    print(f"    Bets placed: {len(bet_results)} ({len(bet_results)/n_games*100:.1f}%)")
    
    if bet_results:
        bet_ev = [b["ev_pct"] for b in bet_results]
        won = sum(1 for b in bet_results if b["won"])
        
        print(f"\n  Bet Performance:")
        print(f"    Avg EV: {np.mean(bet_ev):+.1f}%")
        print(f"    Win rate: {won/len(bet_results)*100:.1f}%")
        
        # Calculate actual profit
        profit = 0
        for b in bet_results:
            if b["won"]:
                odds = b["odds"]
                if odds > 0:
                    profit += odds / 100
                else:
                    profit += 100 / abs(odds)
            else:
                profit -= 1
        
        roi = (profit / len(bet_results)) * 100
        print(f"    Profit: ${profit:.2f}")
        print(f"    ROI: {roi:+.1f}%")
    
    return results, bet_results


if __name__ == "__main__":
    # Test market simulation
    test_market_simulation()
    
    # Run backtest
    results, bets = simulate_backtest(500)
    
    print("\n" + "="*60)
    print("  VALIDATION CHECK")
    print("="*60)
    
    if bets:
        bet_rate = len(bets) / 500 * 100
        if 5 < bet_rate < 25:
            print(f"\n[PASS] Bet frequency {bet_rate:.1f}% is reasonable (target: 10-20%)")
        else:
            print(f"\n[WARN] Bet frequency {bet_rate:.1f}% outside target range")
        
        if np.mean([b["ev_pct"] for b in bets]) > 0:
            print("[PASS] Average EV of bets is positive")
        else:
            print("[FAIL] Average EV of bets is negative")
    else:
        print("\n[FAIL] No bets placed - model edge too small")
"""
MLB Betting Odds Integration
Uses The Odds API and simulates realistic odds for backtesting
"""

import logging
from typing import List, Dict, Optional, Any
from datetime import datetime
import numpy as np
import httpx

logger = logging.getLogger(__name__)

# The Odds API supports MLB
ODDS_API_SPORT_MAP = {
    "mlb": "baseball_mlb",
}


class OddsAPI:
    """Betting odds from The Odds API"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.base_url = "https://api.the-odds-api.com/v4"
        self._client: Optional[httpx.Client] = None
    
    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(headers={"apikey": self.api_key}, timeout=15)
        return self._client
    
    def close(self):
        if self._client:
            self._client.close()
            self._client = None
    
    def get_odds(self, sport: str = "baseball_mlb", regions: str = "us") -> Dict:
        """Get current odds for MLB"""
        try:
            response = self.client.get(
                f"{self.base_url}/sports/{sport}/odds",
                params={"regions": regions, "markets": "h2h,runline,totals"}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.warning(f"Odds API error: {e}")
            return {}
    
    def get_historical_odds(self, sport: str, date: str) -> Dict:
        """Get odds at historical date"""
        # The Odds API has historical but limited - might need alternative
        return self.get_odds(sport)


class MLBOddsSimulator:
    """
    Realistic MLB odds simulation for backtesting
    Based on typical bookmaker behavior
    """
    
    def __init__(self, seed: Optional[int] = None):
        self.rng = np.random.default_rng(seed)
    
    def generate_moneyline_odds(
        self,
        home_win_prob: float,
        away_win_prob: float,
        home_team: str = "Home",
        away_team: str = "Away",
        venue_factor: float = 0.02  # Home field advantage
    ) -> Dict:
        """
        Generate realistic MLB moneyline odds
        
        MLB moneyline typically ranges:
        - Favorite: -150 to -300 (implied 60-75%)
        - Underdog: +100 to +200 (implied 33-50%)
        - Even: around -105/+105 (implied ~50%)
        """
        # Adjust for home field advantage
        home_adj = home_win_prob + venue_factor * (1 - home_win_prob)
        away_adj = away_win_prob - venue_factor * home_win_prob
        
        # Ensure valid probabilities
        home_adj = max(0.05, min(0.95, home_adj))
        away_adj = max(0.05, min(0.95, away_adj))
        
        # Normalize
        total = home_adj + away_adj
        home_prob = home_adj / total
        away_prob = away_adj / total
        
        # Apply typical MLB juice (around 10%)
        juice = 1.10
        home_odds = self._prob_to_ml(home_prob * juice)
        away_odds = self._prob_to_ml(away_prob * juice)
        
        # Add small noise (±3%)
        home_odds = round(home_odds * self.rng.uniform(0.97, 1.03))
        away_odds = round(away_odds * self.rng.uniform(0.97, 1.03))
        
        return {
            "home_team": home_team,
            "away_team": away_team,
            "home_ml": home_odds,
            "away_ml": away_odds,
            "implied_home": round(1 / self._ml_to_decimal(home_odds), 3),
            "implied_away": round(1 / self._ml_to_decimal(away_odds), 3),
        }
    
    def generate_totals_odds(
        self,
        over_prob: float,
        total_line: float = 7.5
    ) -> Dict:
        """Generate over/under totals odds"""
        # Standard over/under is typically -110 both sides
        #juice = 1.10  # -110 = 1.909 decimal
        
        # If model thinks over is more likely, adjust odds
        if over_prob > 0.55:
            over_odds = -115
            under_odds = -105
        elif over_prob < 0.45:
            over_odds = -105
            under_odds = -115
        else:
            over_odds = -110
            under_odds = -110
        
        # Add noise
        over_odds += int(self.rng.integers(-3, 4))
        under_odds += int(self.rng.integers(-3, 4))
        
        return {
            "total_line": total_line,
            "over_odds": over_odds,
            "under_odds": under_odds,
            "over_decimal": self._ml_to_decimal(over_odds),
            "under_decimal": self._ml_to_decimal(under_odds),
            "implied_over": round(1 / self._ml_to_decimal(over_odds), 3),
            "implied_under": round(1 / self._ml_to_decimal(under_odds), 3),
        }
    
    def generate_runline_odds(
        self,
        favorite_prob: float,
        spread: float = 1.5
    ) -> Dict:
        """Generate runline odds (like point spread)"""
        # Common runlines: -1.5 or +1.5
        # Odds typically around -110 to -130
        
        if favorite_prob > 0.7:
            fav_odds = -150  # Heavy favorite
            dog_odds = +130
        elif favorite_prob > 0.6:
            fav_odds = -130
            dog_odds = +110
        else:
            fav_odds = -110
            dog_odds = -110
        
        return {
            "spread": spread,
            "favorite_runline": f"{'-' if spread > 0 else '+'}{abs(spread)}",
            "fav_odds": fav_odds,
            "dog_odds": dog_odds,
            "favorite_decimal": self._ml_to_decimal(fav_odds),
            "dog_decimal": self._ml_to_decimal(dog_odds),
        }
    
    def _prob_to_ml(self, prob: float) -> int:
        """Convert probability to American moneyline"""
        if prob >= 0.5:
            return int(-(prob / (1 - prob)) * 100)
        else:
            return int(((1 - prob) / prob) * 100)
    
    def _ml_to_decimal(self, ml: int) -> float:
        """Convert American moneyline to decimal"""
        if ml > 0:
            return 1 + (ml / 100)
        else:
            return 1 + (100 / abs(ml))


class MLBIntelligenceEngine:
    """
    Complete MLB intelligence layer
    Combines odds, EV calculations, and predictions
    """
    
    def __init__(self, use_api: bool = False, api_key: Optional[str] = None):
        self.use_api = use_api
        self.odds_api = OddsAPI(api_key) if use_api else None
        self.simulator = MLBOddsSimulator()
    
    def get_game_odds(
        self,
        game_pk: int,
        home_win_prob: float,
        away_win_prob: float,
        over_prob: float = 0.5,
        total_line: float = 7.5
    ) -> Dict:
        """Get comprehensive odds for a game"""
        if self.use_api and self.odds_api:
            # Try real API first
            api_data = self.odds_api.get_odds()
            if api_data:
                # Process real data
                pass
        
        # Fall back to simulation
        ml_odds = self.simulator.generate_moneyline_odds(home_win_prob, away_win_prob)
        totals = self.simulator.generate_totals_odds(over_prob, total_line)
        runline = self.simulator.generate_runline_odds(home_win_prob - away_win_prob)
        
        return {
            "game_pk": game_pk,
            "moneyline": ml_odds,
            "totals": totals,
            "runline": runline,
            "source": "simulated"
        }
    
    def calculate_ev(
        self,
        model_prob: float,
        odds_american: int,
        bet_size: float = 1.0
    ) -> Dict:
        """Calculate Expected Value"""
        # Convert American odds to decimal
        if odds_american > 0:
            decimal_odds = 1 + (odds_american / 100)
        else:
            decimal_odds = 1 + (100 / abs(odds_american))
        
        # EV calculation
        # EV = (P(win) * profit) - (P(lose) * stake)
        win_prob = model_prob
        lose_prob = 1 - model_prob
        
        profit = bet_size * (decimal_odds - 1)  # How much you win
        loss = bet_size  # How much you lose
        
        ev = (win_prob * profit) - (lose_prob * loss)
        ev_pct = (ev / bet_size) * 100  # EV as percentage of stake
        
        # Determine if +EV
        is_positive_ev = ev > 0
        
        return {
            "model_prob": model_prob,
            "odds_american": odds_american,
            "odds_decimal": decimal_odds,
            "ev": ev,
            "ev_pct": ev_pct,
            "is_positive_ev": is_positive_ev,
            "edge": (model_prob * decimal_odds) - 1
        }
    
    def calculate_clv(
        self,
        predicted_prob: float,
        closing_odds_american: int,
        opening_odds_american: Optional[int] = None
    ) -> Dict:
        """Calculate Closing Line Value"""
        # Convert closing odds to probability
        if closing_odds_american > 0:
            closing_implied = 1 / (1 + closing_odds_american / 100)
        else:
            closing_implied = 1 / (1 + 100 / abs(closing_odds_american))
        
        # CLV = Model probability - Closing implied probability
        clv = predicted_prob - closing_implied
        clv_pct = clv * 100
        
        # If opening odds available, also track line movement
        line_movement = None
        if opening_odds_american:
            if opening_odds_american > 0:
                opening_implied = 1 / (1 + opening_odds_american / 100)
            else:
                opening_implied = 1 / (1 + 100 / abs(opening_odds_american))
            line_movement = closing_implied - opening_implied
        
        return {
            "predicted_prob": predicted_prob,
            "closing_implied": closing_implied,
            "clv": clv,
            "clv_pct": clv_pct,
            "clv_percentage": (clv / max(closing_implied, 0.01)) * 100 if closing_implied > 0 else 0,
            "line_movement": line_movement,
            "verdict": "WINNER" if clv > 0 else "LOSER"
        }
    
    def analyze_bet(
        self,
        model_prob: float,
        odds_american: int,
        threshold: float = 0.52  # Need 52%+ to overcome juice
    ) -> Dict:
        """Complete bet analysis with EV and recommendation"""
        # Calculate EV
        ev_data = self.calculate_ev(model_prob, odds_american)
        
        # Determine recommendation
        if model_prob < threshold:
            recommendation = "PASS"
            reason = f"Model probability {model_prob:.1%} below threshold {threshold:.1%}"
        elif not ev_data["is_positive_ev"]:
            recommendation = "PASS"
            reason = f"Negative EV: {ev_data['ev_pct']:+.1f}%"
        elif ev_data["ev_pct"] >= 10:
            recommendation = "BET LARGE"
            reason = f"Strong +EV: {ev_data['ev_pct']:+.1f}%"
        elif ev_data["ev_pct"] >= 5:
            recommendation = "BET"
            reason = f"Positive EV: {ev_data['ev_pct']:+.1f}%"
        else:
            recommendation = "PAUSE"
            reason = "Near break-even - wait for better line"
        
        return {
            "recommendation": recommendation,
            "reason": reason,
            "model_prob": model_prob,
            "odds": odds_american,
            "ev": ev_data["ev"],
            "ev_pct": ev_data["ev_pct"],
            "edge": ev_data["edge"]
        }
    
    def close(self):
        if self.odds_api:
            self.odds_api.close()


# =============================================================================
# MLB Market Calibrator
# =============================================================================

class MLBCalibrator:
    """
    Calibration specifically for MLB markets
    Different calibration needed for:
    - Moneyline
    - Totals (Over/Under)
    - Runline
    - Player props
    """
    
    def __init__(self, market: str = "moneyline"):
        self.market = market
        self.calibration_curves = {}
    
    def calibrate_probability(
        self,
        predicted_prob: float,
        market: str,
        factors: Optional[Dict] = None
    ) -> float:
        """
        Calibrate probability for specific MLB market
        Applies adjustments based on known biases
        """
        factors = factors or {}
        
        if market == "moneyline":
            # Moneyline typically underestimates home dogs
            home_favorite = factors.get("home_favorite", False)
            if home_favorite:
                # Favorites win more than implied
                return predicted_prob * 1.02
            
        elif market == "totals":
            # Totals tend to go OVER in hitter-friendly parks
            # and UNDER in pitcher-friendly parks
            park_factor = factors.get("park_factor", 1.0)
            if park_factor > 1.1:  # Hitter friendly
                return min(0.6, predicted_prob * 1.05)
            elif park_factor < 0.9:  # Pitcher friendly
                return max(0.4, predicted_prob * 0.95)
        
        elif market == "runline":
            # Runline favorites win by more than 1.5 less often than expected
            return predicted_prob * 0.95
        
        return predicted_prob
    
    def get_calibration_curve(self, market: str) -> List[Dict]:
        """Get historical calibration curve for market"""
        # Simplified - would use actual data
        return [
            {"bin_start": 0.0, "bin_end": 0.2, "actual": 0.15},
            {"bin_start": 0.2, "bin_end": 0.4, "actual": 0.32},
            {"bin_start": 0.4, "bin_end": 0.6, "actual": 0.52},
            {"bin_start": 0.6, "bin_end": 0.8, "actual": 0.72},
            {"bin_start": 0.8, "bin_end": 1.0, "actual": 0.88},
        ]


if __name__ == "__main__":
    print("=== MLB Intelligence Testing ===\n")
    
    engine = MLBOddsSimulator()
    
    # Test moneyline generation
    print("Moneyline (model says 55% home win):")
    ml = engine.generate_moneyline_odds(0.55, 0.45)
    print(f"  {ml['away_team']}: {ml['away_ml']} (implied {ml['implied_away']:.1%})")
    print(f"  {ml['home_team']}: {ml['home_ml']} (implied {ml['implied_home']:.1%})")
    
    # Test totals
    print("\nTotals (8.5):")
    totals = engine.generate_totals_odds(0.52, 8.5)
    print(f"  Over 8.5: {totals['over_odds']} (implied {totals['implied_over']:.1%})")
    print(f"  Under 8.5: {totals['under_odds']} (implied {totals['implied_under']:.1%})")
    
    # Test EV calculation
    intel = MLBIntelligenceEngine()
    print("\nEV Analysis (55% win prob, -120 odds):")
    ev = intel.calculate_ev(0.55, -120)
    print(f"  Decimal: {ev['odds_decimal']:.2f}")
    print(f"  EV: ${ev['ev']:.2f} per $1 bet ({ev['ev_pct']:+.1f}%)")
    print(f"  Edge: {ev['edge']:+.2f}")
    print(f"  +EV: {ev['is_positive_ev']}")
    
    # Test bet analysis
    print("\nBet Analysis:")
    analysis = intel.analyze_bet(0.58, -130)
    print(f"  Recommendation: {analysis['recommendation']}")
    print(f"  Reason: {analysis['reason']}")
    
    intel.close()
    print("\n[COMPLETE]")
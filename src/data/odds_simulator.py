"""
Realistic Odds Simulator for Backtesting

Simulates realistic bookmaker odds based on:
- Base probability from model prediction
- Typical vig (juice) of 5-7%
- Home bias in odds
- Random market noise
"""

import numpy as np
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class OddsSimulator:
    """
    Realistic odds simulation for backtesting.
    
    Generates odds that reflect actual bookmaker behavior:
    - 5-7% typical juice
    - Home team bias (slight)
    - Movement based on prediction confidence
    """
    
    VIG_RANGE = (1.05, 1.07)  # Bookmaker margin
    HOME_BIAS = 0.03  # Slight home favorite bias
    
    def __init__(self, seed: Optional[int] = None):
        self.rng = np.random.default_rng(seed)
    
    def generate_odds(
        self, 
        model_prob: float, 
        actual_home_win: Optional[bool] = None,
        home_team: str = "Home",
        away_team: str = "Away"
    ) -> dict:
        """
        Generate realistic 3-way odds.
        
        Args:
            model_prob: Model's predicted probability of over 2.5 goals
            actual_home_win: Actual outcome (for backtesting - None for live)
            home_team: Home team name
            away_team: Away team name
            
        Returns:
            dict with odds and implied probabilities
        """
        # Base: assume 50/50 for home/draw/away baseline
        base_probs = [0.45, 0.28, 0.27]  # home, draw, away
        
        # Adjust for model prediction (our edge is on over 2.5)
        # Over 2.5 is roughly correlated with away wins and more goals
        if model_prob > 0.5:
            # Higher scoring game expected - slight away bias
            base_probs[2] += 0.05
            base_probs[1] += 0.03
            base_probs[0] -= 0.08
        
        # Normalize
        total = sum(base_probs)
        base_probs = [p/total for p in base_probs]
        
        # Add vig (bookmaker margin)
        vig = self.rng.uniform(*self.VIG_RANGE)
        
        # Convert to decimal odds
        fair_odds = [1/p for p in base_probs]
        bookmaker_odds = [o * vig for o in fair_odds]
        
        # Add small random noise (±3%)
        noise = self.rng.uniform(0.97, 1.03, 3)
        bookmaker_odds = [o * n for o, n in zip(bookmaker_odds, noise)]
        
        home_odds, draw_odds, away_odds = sorted(bookmaker_odds, reverse=True)
        
        # Keep within reasonable bounds
        home_odds = max(1.10, min(15.0, home_odds))
        draw_odds = max(2.50, min(10.0, draw_odds))
        away_odds = max(1.10, min(15.0, away_odds))
        
        return {
            "home_team": home_team,
            "away_team": away_team,
            "home_odds": round(home_odds, 2),
            "draw_odds": round(draw_odds, 2),
            "away_odds": round(away_odds, 2),
            "implied_home": round(1/home_odds, 3),
            "implied_draw": round(1/draw_odds, 3),
            "implied_away": round(1/away_odds, 3),
            "over_25_odds": self._estimate_over_25_odds(model_prob),
            "model_prob": model_prob,
            "vig": round((vig - 1) * 100, 1)
        }
    
    def _estimate_over_25_odds(self, model_prob: float) -> float:
        """Estimate over 2.5 goals odds from model probability"""
        # Apply typical bookmaker margin to over 2.5
        vig = self.rng.uniform(*self.VIG_RANGE)
        
        # Add some variance based on confidence
        if model_prob > 0.7:
            # High confidence - tighter spread
            variance = self.rng.uniform(-0.02, 0.05)
        elif model_prob > 0.5:
            variance = self.rng.uniform(-0.05, 0.08)
        else:
            variance = self.rng.uniform(-0.08, 0.10)
        
        adjusted_prob = model_prob + variance
        adjusted_prob = max(0.1, min(0.9, adjusted_prob))
        
        return round(adjusted_prob * vig, 2)
    
    def get_over_25_odds(
        self, 
        model_prob: float, 
        league: str = "BL1"
    ) -> float:
        """Get over 2.5 goals odds with league-specific adjustments"""
        
        # League-specific adjustments based on typical scoring
        league_factors = {
            "BL1": 1.02,   # High scoring - slightly lower odds
            "PL": 1.00,    # Baseline
            "PD": 1.00,    # Baseline  
            "SA": 0.98,    # Low scoring - slightly higher odds
            "FL1": 0.99,   # Slightly lower
        }
        
        factor = league_factors.get(league, 1.0)
        odds = self._estimate_over_25_odds(model_prob * factor)
        
        # Typical over 2.5 range: 1.50 - 3.00
        return round(max(1.50, min(3.00, odds)), 2)


class OddsManager:
    """
    Manages odds retrieval from multiple sources:
    1. Real API (The Odds API when available)
    2. Historical database
    3. Simulated (for backtesting)
    """
    
    def __init__(self, use_real_api: bool = True):
        self.simulator = OddsSimulator()
        self._api_client = None
        self.use_real_api = use_real_api
        
        # League to sport key mapping
        self.sport_map = {
            "BL1": "soccer_germany_bundesliga",
            "PL": "soccer_england_premier_league", 
            "SA": "soccer_italy_serie_a",
            "FL1": "soccer_france_ligue_1",
            "PD": "soccer_spain_la_liga"
        }
    
    @property
    def api_client(self):
        if self._api_client is None:
            from src.data.odds_client import OddsAPIClient
            self._api_client = OddsAPIClient()
        return self._api_client
    
    def get_odds(
        self, 
        fixture_id: int,
        league: str,
        model_prob: float,
        home_team: str = "Home",
        away_team: str = "Away",
        use_cache: bool = True
    ) -> dict:
        """
        Get odds for a fixture.
        
        Tries: 1) Real API, 2) Database, 3) Simulated
        """
        # Try real API first
        if self.use_real_api:
            try:
                real_odds = self._fetch_from_api(fixture_id, league)
                if real_odds:
                    real_odds["source"] = "api"
                    return real_odds
            except Exception as e:
                logger.debug(f"API fetch failed: {e}")
        
        # Fall back to simulation
        odds = self.simulator.generate_odds(
            model_prob=model_prob,
            home_team=home_team,
            away_team=away_team
        )
        odds["source"] = "simulated"
        odds["fixture_id"] = fixture_id
        return odds
    
    def get_over_25_odds(
        self,
        league: str,
        model_prob: float
    ) -> float:
        """Get over 2.5 goals odds with league-specific adjustments"""
        
        # League-specific adjustments based on typical scoring
        league_factors = {
            "BL1": 1.02,   # High scoring - slightly lower odds
            "PL": 1.00,    # Baseline
            "PD": 1.00,    # Baseline  
            "SA": 0.95,    # Low scoring - slightly higher odds
            "FL1": 0.98,   # Slightly lower
        }
        
        factor = league_factors.get(league, 1.0)
        
        # Base over 2.5 is typically around 1.85-2.00 for 50% prob
        # Convert model probability to odds (accounting for vig)
        vig = 1.06  # 6% typical vig
        
        # Map probability to odds range: 0.1 -> 2.80, 0.9 -> 1.55
        # This gives realistic over 2.5 odds
        if model_prob >= 0.5:
            # 0.5 -> 2.00, 0.9 -> 1.55
            base_odds = 2.00 - (model_prob - 0.5) * 1.125
        else:
            # 0.1 -> 2.80, 0.5 -> 2.00  
            base_odds = 2.80 - (model_prob - 0.1) * 2.0
        
        # Apply league factor
        adjusted_odds = base_odds * factor
        
        return round(max(1.55, min(2.80, adjusted_odds)), 2)
    
    def _fetch_from_api(self, fixture_id: int, league: str) -> Optional[dict]:
        """Try to fetch real odds from API"""
        if not self.api_client.is_available():
            return None
            
        sport = self.sport_map.get(league)
        if not sport:
            return None
            
        data = self.api_client.get_odds(sport)
        if not data or "data" not in data:
            return None
            
        # Find matching fixture
        for event in data.get("data", []):
            if str(event.get("id")) == str(fixture_id):
                # Extract best available odds
                bookmakers = event.get("bookmakers", [])
                if not bookmakers:
                    return None
                    
                bm = bookmakers[0]  # Use first bookmaker
                h2h = bm.get("markets", [{}])[0].get("outcomes", [])
                
                home_odds = None
                draw_odds = None  
                away_odds = None
                
                for o in h2h:
                    if o.get("name") == event.get("home_team"):
                        home_odds = o.get("price")
                    elif o.get("name") == "Draw":
                        draw_odds = o.get("price")
                    elif o.get("name") == event.get("away_team"):
                        away_odds = o.get("price")
                
                if home_odds and away_odds:
                    return {
                        "home_odds": float(home_odds),
                        "draw_odds": float(draw_odds) if draw_odds else 3.0,
                        "away_odds": float(away_odds),
                        "bookmaker": bm.get("title"),
                        "fixture_id": fixture_id
                    }
        
        return None
    
    def close(self):
        if self._api_client:
            self._api_client.close()
            self._api_client = None
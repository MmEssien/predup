"""
MLB Odds Abstraction Layer

Provides unified interface for betting odds:
1. The Odds API (primary - real odds)
2. API-Sports (secondary - if available)
3. Synthetic Market Model (fallback)

Can be extended to add more providers.
"""

import sys
from pathlib import Path
_root = Path(r"C:\Users\Strategic Shelter\.antigravity\AI\PredUp")
sys.path.insert(0, str(_root))

import os
import numpy as np
import random
import logging
from typing import Dict, Optional
from abc import ABC, abstractmethod
from dotenv import load_dotenv

load_dotenv(_root / ".env")
logger = logging.getLogger(__name__)


class BaseOddsProvider(ABC):
    """Abstract base class for odds providers"""
    
    @abstractmethod
    def get_odds(self, home_team: str, away_team: str, game_date: str = None) -> Optional[Dict]:
        """Get odds for a game. Returns None if unavailable."""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is working"""
        pass


class SyntheticMarketProvider(BaseOddsProvider):
    """
    Synthetic MLB market model - realistic bookmaker simulation
    
    Used when real odds are unavailable.
    Generates statistically realistic odds for testing/backtesting.
    
    Parameters (adjustable for testing):
    - Overround: 3-5% (lower than typical for backtest viability)
    - Favorite bias: 3% (reduced)
    - Noise: ±3-6% random market inefficiency
    """
    
    def __init__(self, seed: int = None, low_vig: bool = True):
        self.rng = np.random.default_rng(seed)
        
        # Market parameters - adjusted for backtest viability
        if low_vig:
            self.overround_range = (0.03, 0.05)  # 3-5% (lower for testing)
            self.favorite_bias = 0.03  # 3%
        else:
            self.overround_range = (0.05, 0.08)  # 5-8% realistic
            self.favorite_bias = 0.05  # 5%
        
        self.noise_range = (-0.03, 0.06)  # ±3-6%
        self.noise_probability = 0.15  # 15% of lines have noise
        
        self._name = "SyntheticMarket"
    
    def is_available(self) -> bool:
        return True
    
    def get_odds(self, home_team: str, away_team: str, 
                model_prob_home: float = None, game_id: int = None) -> Optional[Dict]:
        """
        Generate synthetic market odds.
        
        Args:
            home_team: Home team name
            away_team: Away team name  
            model_prob_home: Model's predicted probability (optional)
            game_id: Not used for synthetic (compatibility with interface)
        
        Returns:
            Dict with odds or None
        """
        if model_prob_home is None:
            model_prob_home = 0.5 + (self.rng.random() - 0.5) * 0.2
        
        # Clamp to valid range
        prob_home = np.clip(model_prob_home, 0.1, 0.9)
        prob_away = 1 - prob_home
        
        # Apply favorite bias
        if prob_home > 0.5:
            bias = self.favorite_bias * (prob_home - 0.5) * 2
            prob_home = prob_home - bias
            prob_away = 1 - prob_home
        else:
            bias = self.favorite_bias * (prob_away - 0.5) * 2
            prob_away = prob_away - bias
            prob_home = 1 - prob_away
        
        # Normalize
        total_prob = prob_home + prob_away
        prob_home = prob_home / total_prob * (1 + self.rng.uniform(*self.overround_range))
        prob_away = 1 - prob_home
        
        # Apply noise
        if self.rng.random() < self.noise_probability:
            noise = self.rng.uniform(*self.noise_range)
            prob_home = np.clip(prob_home + noise, 0.15, 0.85)
            prob_away = 1 - prob_home
        
        # Convert to American odds
        odds_home = self._prob_to_ml(prob_home)
        odds_away = self._prob_to_ml(prob_away)
        
        # Calculate implied probability
        implied_home = self._ml_to_prob(odds_home)
        
        return {
            "home_team": home_team,
            "away_team": away_team,
            "home_odds": odds_home,
            "away_odds": odds_away,
            "implied_home": implied_home,
            "overround_pct": (prob_home + prob_away - 1) * 100,
            "source": self._name,
            "type": "synthetic"
        }
    
    def _prob_to_ml(self, prob: float) -> int:
        """Probability to American moneyline"""
        if prob >= 0.5:
            return int(-(prob / (1 - prob)) * 100)
        else:
            return int(((1 - prob) / prob) * 100)
    
    def _ml_to_prob(self, ml: int) -> float:
        """American moneyline to probability"""
        if ml > 0:
            return 1 / (1 + ml / 100)
        else:
            return 1 / (1 + 100 / abs(ml))


class TheOddsAPIProvider(BaseOddsProvider):
    """
    The Odds API provider (api.the-odds-api.com)
    
    Uses real betting odds from multiple bookmakers.
    Key format: apiKey as query parameter (camelCase)
    """
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("ODDS_API_KEY") or "dca7069462322213519c88f447526adc"
        self.base_url = "https://api.the-odds-api.com/v4"
        self._client = None
        self._checked = False
        self._available = False
        self._cached_odds = None
        self._cache_time = None
    
    def is_available(self) -> bool:
        if not self._checked:
            self._check_availability()
        return self._available
    
    def _check_availability(self):
        try:
            import httpx
            client = httpx.Client(timeout=15)
            resp = client.get(f"{self.base_url}/sports", params={"apiKey": self.api_key})
            client.close()
            
            if resp.status_code == 200:
                self._available = True
                logger.info("The Odds API is working")
            else:
                self._available = False
                logger.warning("The Odds API check failed")
        except Exception as e:
            logger.error(f"The Odds API check error: {e}")
            self._available = False
        finally:
            self._checked = True
    
    def get_odds(self, home_team: str, away_team: str,
                model_prob_home: float = None, game_id: int = None) -> Optional[Dict]:
        """Get odds from The Odds API"""
        if not self.is_available():
            return None
        
        try:
            import httpx
            client = httpx.Client(timeout=15)
            
            # Get MLB odds
            resp = client.get(
                f"{self.base_url}/sports/baseball_mlb/odds",
                params={
                    "apiKey": self.api_key,
                    "regions": "us",
                    "markets": "h2h"
                }
            )
            client.close()
            
            if resp.status_code != 200:
                return None
            
            data = resp.json()
            
            # Find matching game
            for event in data:
                event_home = event.get("home_team", "")
                event_away = event.get("away_team", "")
                
                # Partial match
                if home_team.lower() in event_home.lower() or event_home.lower() in home_team.lower():
                    if away_team.lower() in event_away.lower() or event_away.lower() in away_team.lower():
                        
                        # Get best odds
                        bookmakers = event.get("bookmakers", [])
                        if not bookmakers:
                            continue
                        
                        best_home_odds = None
                        best_away_odds = None
                        best_bookmaker = None
                        
                        for bm in bookmakers:
                            for market in bm.get("markets", []):
                                if market.get("key") != "h2h":
                                    continue
                                for outcome in market.get("outcomes", []):
                                    name = outcome.get("name", "")
                                    price = outcome.get("price")
                                    
                                    if name == event_home or name in event_home:
                                        if price and (best_home_odds is None or price > best_home_odds):
                                            best_home_odds = price
                                            best_bookmaker = bm.get("title")
                                    elif name == event_away or name in event_away:
                                        if price and (best_away_odds is None or price > best_away_odds):
                                            best_away_odds = price
                                            best_bookmaker = bm.get("title")
                        
                        if best_home_odds and best_away_odds:
                            # Convert decimal to implied probability
                            implied_home = 1 / best_home_odds
                            
                            return {
                                "home_team": event_home,
                                "away_team": event_away,
                                "home_odds": best_home_odds,  # Decimal odds
                                "away_odds": best_away_odds,
                                "implied_home": implied_home,
                                "bookmaker": best_bookmaker,
                                "source": "the_odds_api",
                                "type": "real",
                                "odds_format": "decimal"
                            }
            
        except Exception as e:
            logger.error(f"The Odds API error: {e}")
        
        return None


class APISportsOddsProvider(BaseOddsProvider):
    """
    API-Sports odds provider
    
    Note: Odds may not be available on free plan.
    """
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("API_FOOTBALL_COM_KEY")
        self.base_url = "https://v1.baseball.api-sports.io"
        self._client = None
        self._checked = False
        self._available = False
    
    def is_available(self) -> bool:
        if not self._checked:
            self._check_availability()
        return self._available
    
    def _check_availability(self):
        """Check if API-Sports returns odds"""
        try:
            import httpx
            client = httpx.Client(headers={"x-apisports-key": self.api_key}, timeout=15)
            
            # Test with a known game
            resp = client.get(f"{self.base_url}/odds", params={"game": 152753})
            result = resp.json()
            
            if result.get("results", 0) > 0:
                self._available = True
                logger.info("API-Sports odds available")
            else:
                self._available = False
                logger.warning("API-Sports odds NOT available on free plan")
            
            client.close()
        except Exception as e:
            logger.error(f"API-Sports check failed: {e}")
            self._available = False
        finally:
            self._checked = True
    
    def get_odds(self, home_team: str, away_team: str, game_id: int = None) -> Optional[Dict]:
        """Get odds from API-Sports"""
        if not self.is_available() or game_id is None:
            return None
        
        try:
            import httpx
            client = httpx.Client(headers={"x-apisports-key": self.api_key}, timeout=15)
            
            resp = client.get(f"{self.base_url}/odds", params={"game": game_id})
            result = resp.json()
            client.close()
            
            if result.get("results", 0) > 0:
                # Parse first bookmaker's odds
                bm = result["response"][0]
                odds_data = bm.get("odds", [])
                
                home_odds = None
                away_odds = None
                
                for o in odds_data:
                    label = o.get("label", "").lower()
                    value = o.get("value")
                    
                    if "home" in label and value:
                        home_odds = value
                    elif "away" in label and value:
                        away_odds = value
                
                if home_odds and away_odds:
                    return {
                        "home_team": home_team,
                        "away_team": away_team,
                        "home_odds": home_odds,
                        "away_odds": away_odds,
                        "implied_home": self._ml_to_prob(home_odds),
                        "source": "api_sports",
                        "type": "real",
                        "bookmaker": bm.get("name", "unknown")
                    }
        except Exception as e:
            logger.error(f"API-Sports odds error: {e}")
        
        return None
    
    def _ml_to_prob(self, ml: int) -> float:
        if ml > 0:
            return 1 / (1 + ml / 100)
        else:
            return 1 / (1 + 100 / abs(ml))


class OddsAdapter:
    """
    Unified odds adapter with provider chain
    
    Tries providers in order, uses first available.
    Fallback chain:
    1. The Odds API (real odds)
    2. API-Sports (if available)
    3. Synthetic Market (testing/backtesting)
    """
    
    def __init__(self, prefer_synthetic: bool = False):
        self.providers: list[BaseOddsProvider] = []
        
        # Initialize providers in priority order
        if not prefer_synthetic:
            self.providers.append(TheOddsAPIProvider())  # Primary: real odds
            self.providers.append(APISportsOddsProvider())  # Secondary
        
        self.providers.append(SyntheticMarketProvider())  # Fallback
        
        self._primary_provider = None
        self._find_available()
    
    def _find_available(self):
        """Find first available provider"""
        for p in self.providers:
            if p.is_available():
                self._primary_provider = p
                logger.info(f"Primary odds provider: {type(p).__name__}")
                break
    
    def get_odds(self, home_team: str, away_team: str, 
               model_prob_home: float = None, game_id: int = None) -> Optional[Dict]:
        """
        Get odds using available provider.
        
        Args:
            home_team: Home team name
            away_team: Away team name
            model_prob_home: Model probability (for synthetic fallback)
            game_id: Game ID (for API lookup)
        
        Returns:
            Dict with odds or None
        """
        # Try primary provider first
        if self._primary_provider:
            odds = self._primary_provider.get_odds(home_team, away_team, model_prob_home, game_id)
            if odds:
                return odds
        
        # Fallback to synthetic
        for p in self.providers:
            if isinstance(p, SyntheticMarketProvider):
                odds = p.get_odds(home_team, away_team, model_prob_home)
                if odds:
                    odds["fallback"] = True
                    return odds
        
        return None
    
    def current_provider(self) -> str:
        """Get name of current primary provider"""
        if self._primary_provider:
            return type(self._primary_provider).__name__
        return "None"


class EVCalculator:
    """Expected value calculator for odds"""
    
    @staticmethod
    def calculate(model_prob: float, market_odds) -> Dict:
        """
        Calculate expected value of a bet.
        
        Args:
            model_prob: Model's predicted probability (0-1)
            market_odds: Either American moneyline or decimal odds
        
        Returns:
            Dict with EV metrics
        """
        # Detect odds format
        # Decimal odds are typically < 10 (e.g., 1.5, 2.0, 3.5)
        # American odds are > 100 or < -100 (e.g., -150, +200)
        if isinstance(market_odds, float):
            decimal = market_odds
        elif market_odds > 0 and market_odds <= 10:
            # Decimal odds (likely)
            decimal = market_odds
        elif market_odds > 0 and market_odds > 10:
            # American positive odds -> convert to decimal
            decimal = 1 + market_odds / 100
        elif market_odds < 0:
            # American negative odds -> convert to decimal
            decimal = 1 + 100 / abs(market_odds)
        else:
            decimal = 2.0  # Default fallback
        
        # Calculate implied probability
        implied = 1 / decimal
        
        # EV formula
        ev = model_prob * (decimal - 1) - (1 - model_prob)
        ev_pct = ev * 100
        
        # Edge
        edge = model_prob - implied
        
        return {
            "model_prob": model_prob,
            "market_odds": market_odds,
            "decimal_odds": decimal,
            "implied_prob": implied,
            "ev": ev,
            "ev_pct": ev_pct,
            "edge": edge,
            "is_positive_ev": ev > 0,
            "kelly_fraction": model_prob - (1 - model_prob) / (decimal - 1) if decimal > 1 else 0
        }
    
    @staticmethod
    def analyze_bet(model_prob: float, market_odds, 
                    threshold: float = 5.0) -> Dict:
        """Analyze if a bet meets criteria."""
        ev_data = EVCalculator.calculate(model_prob, market_odds)
        
        return {
            **ev_data,
            "qualifies": ev_data["is_positive_ev"] and ev_data["ev_pct"] >= threshold,
            "threshold": threshold
        }


def test_odds_abstraction():
    """Test the odds abstraction layer"""
    print("="*70)
    print("  MLB ODDS ABSTRACTION LAYER TEST")
    print("="*70)
    
    adapter = OddsAdapter()
    
    print(f"\n[1] Provider Status")
    print(f"    Primary provider: {adapter.current_provider()}")
    print(f"    Available providers: {len(adapter.providers)}")
    
    print(f"\n[2] Testing odds retrieval...")
    
    test_cases = [
        ("New York Yankees", "Los Angeles Dodgers", 0.55),
        ("Chicago Cubs", "St. Louis Cardinals", 0.48),
        ("Boston Red Sox", "New York Yankees", 0.52),
    ]
    
    for home, away, model_prob in test_cases:
        odds = adapter.get_odds(home, away, model_prob_home=model_prob)
        
        if odds:
            print(f"\n    {home} vs {away}")
            print(f"      Odds: {odds['home_odds']} / {odds['away_odds']}")
            print(f"      Implied: {odds['implied_home']:.1%}")
            print(f"      Source: {odds['source']} ({odds['type']})")
            
            # Calculate EV
            ev = EVCalculator.calculate(model_prob, odds['home_odds'])
            print(f"      Model prob: {model_prob:.1%}")
            print(f"      EV: {ev['ev_pct']:+.1f}%")
            print(f"      Edge: {ev['edge']:+.1%}")
            print(f"      Positive EV: {ev['is_positive_ev']}")
    
    print("\n[3] Synthetic Market Parameters")
    synth = SyntheticMarketProvider(seed=42)
    print(f"    Overround: {synth.overround_range}")
    print(f"    Favorite bias: {synth.favorite_bias}")
    print(f"    Noise range: {synth.noise_range}")
    print(f"    Noise probability: {synth.noise_probability}")
    
    print("\n" + "="*70)
    print("  ODDS ABSTRACTION LAYER READY")
    print("="*70)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_odds_abstraction()
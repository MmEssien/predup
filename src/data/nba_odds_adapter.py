"""
NBA Odds Adapter - Multi-source odds with fallback logic
Uses The Odds API for NBA basketball odds with realistic simulation fallback
"""

import os
import logging
from typing import Optional, Dict, List
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

NBA_SPORT_KEY = "basketball_nba"


class NBAOddsAdapter:
    """
    Multi-source NBA odds adapter with fallback logic:
    1. The Odds API (primary for NBA)
    2. API-Sports odds (fallback - may not be available on free plan)
    3. Realistic simulation (last resort for testing)
    """
    
    def __init__(self, odds_api_key: Optional[str] = None):
        from src.data.odds_client import OddsAPIClient
        
        self.api_key = odds_api_key or os.getenv("ODDS_API_KEY", "dca7069462322213519c88f447526adc")
        self.the_odds = OddsAPIClient(self.api_key)
        self.simulator = None
        self._enabled = bool(self.api_key)
        
        logger.info(f"NBA Odds Adapter initialized with API key: {self.api_key[:10]}..." if self.api_key else "NBA Odds Adapter initialized (no API key)")
    
    def is_available(self) -> bool:
        """Check if odds source is available"""
        if not self._enabled:
            return False
        return self.the_odds.is_available()
    
    def get_odds(self, home_team: str, away_team: str, 
                 true_prob_home: float = None) -> Dict:
        """
        Get NBA odds with multi-source fallback
        
        Returns:
            Dict with odds keys: home_odds, away_odds, implied_home, overround, source, type
        """
        if self.is_available():
            try:
                odds_data = self.the_odds.get_odds(sport=NBA_SPORT_KEY)
                if odds_data and "data" in odds_data:
                    parsed = self._parse_odds(odds_data, home_team, away_team)
                    if parsed:
                        logger.info(f"Got real NBA odds from The Odds API: {parsed}")
                        return {
                            "source": "the_odds_api",
                            "home_odds": parsed["home_odds"],
                            "away_odds": parsed["away_odds"],
                            "implied_home": parsed.get("implied_home"),
                            "overround": parsed.get("overround"),
                            "bookmaker": parsed.get("bookmaker"),
                            "type": "real"
                        }
            except Exception as e:
                logger.error(f"The Odds API failed for NBA: {e}")
        
        if true_prob_home is not None:
            return self._simulate_odds(true_prob_home)
        
        return {
            "source": "none",
            "home_odds": None,
            "away_odds": None,
            "implied_home": None,
            "overround": None,
            "type": "unavailable"
        }
    
    def _parse_odds(self, odds_data: Dict, home_team: str, away_team: str) -> Optional[Dict]:
        """Parse odds data from The Odds API for specific matchup"""
        if not odds_data or "data" not in odds_data:
            return None
        
        for event in odds_data.get("data", []):
            home_name = event.get("home_team", "").lower()
            away_name = event.get("away_team", "").lower()
            
            if home_name in home_team.lower() or home_team.lower() in home_name:
                if away_name in away_team.lower() or away_name.lower() in away_name:
                    bookmakers = event.get("bookmakers", [])
                    if bookmakers:
                        bm = bookmakers[0]
                        outcomes = bm.get("markets", {}).get("h2h", [])
                        
                        home_odds = None
                        away_odds = None
                        
                        for o in outcomes:
                            if o.get("name") == home_team:
                                home_odds = o.get("price")
                            elif o.get("name") == away_team:
                                away_odds = o.get("price")
                        
                        if home_odds and away_odds:
                            implied_home = 1 / home_odds
                            implied_away = 1 / away_odds
                            total_implied = implied_home + implied_away
                            overround = (total_implied - 1) * 100
                            
                            return {
                                "home_odds": home_odds,
                                "away_odds": away_odds,
                                "implied_home": implied_home,
                                "overround": overround,
                                "bookmaker": bm.get("title")
                            }
        
        return None
    
    def _simulate_odds(self, true_prob_home: float) -> Dict:
        """Use realistic market simulator as fallback"""
        from src.intelligence.realistic_market import RealisticMarketOdds
        
        if self.simulator is None:
            self.simulator = RealisticMarketOdds()
        
        odds = self.simulator.generate_moneyline_odds(true_prob_home)
        
        return {
            "source": "simulation",
            "home_odds": odds["odds_home"],
            "away_odds": odds["odds_away"],
            "implied_home": odds["implied_home"],
            "overround": odds["overround_pct"],
            "type": "simulated"
        }
    
    def get_upcoming_games(self, days_ahead: int = 1) -> List[Dict]:
        """Get upcoming NBA games with odds"""
        if not self.is_available():
            return []
        
        try:
            data = self.the_odds.get_upcoming(sport=NBA_SPORT_KEY, days_ahead=days_ahead)
            if data and "data" in data:
                return data["data"]
        except Exception as e:
            logger.error(f"Failed to get upcoming NBA games: {e}")
        
        return []
    
    def get_credits_info(self) -> Dict:
        """Get odds API credits information"""
        return self.the_odds.get_credits_info()
    
    def close(self):
        """Close connections"""
        self.the_odds.close()


def test_nba_odds():
    """Test the NBA odds adapter"""
    adapter = NBAOddsAdapter()
    
    print("\n=== Testing NBA Odds Adapter ===")
    print(f"API available: {adapter.is_available()}")
    
    if adapter.is_available():
        print("\n[1] Testing real odds fetch...")
        test_teams = [
            ("Los Angeles Lakers", "Boston Celtics"),
            ("Golden State Warriors", "Phoenix Suns"),
            ("Miami Heat", "Milwaukee Bucks"),
        ]
        
        for home, away in test_teams:
            odds = adapter.get_odds(home, away)
            print(f"  {home} vs {away}: {odds}")
        
        print("\n[2] Testing upcoming games...")
        games = adapter.get_upcoming_games(days_ahead=1)
        print(f"  Found {len(games)} upcoming games")
        
        print("\n[3] Credits info:")
        print(f"  {adapter.get_credits_info()}")
    else:
        print("\n[1] Testing simulation fallback...")
        for true_prob in [0.4, 0.5, 0.6]:
            odds = adapter.get_odds("Lakers", "Celtics", true_prob_home=true_prob)
            print(f"  True prob {true_prob}: {odds}")
    
    adapter.close()
    print("\n=== Test Complete ===")


if __name__ == "__main__":
    test_nba_odds()
"""
MLB Data Adapter - Uses API-Sports for games/teams, The Odds API for odds
Multi-source adapter with fallback logic
"""

import os
import sys
import httpx
import numpy as np
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

# Add parent to path for imports
from pathlib import Path
_root = Path(__file__).parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)


class APISportsMLBClient:
    """API-Sports client for MLB games, teams, and stats"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("API_FOOTBALL_COM_KEY") or "7f7d0fcbf7fa4d5213acdcf6358d2d95"
        self.base_url = "https://v1.baseball.api-sports.io"
        self._client: Optional[httpx.Client] = None
    
    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                headers={"x-apisports-key": self.api_key},
                timeout=30
            )
        return self._client
    
    def close(self):
        if self._client:
            self._client.close()
            self._client = None
    
    def get_games(self, season: int = 2024, date: str = None, limit: int = 100) -> List[Dict]:
        """Get MLB games"""
        params = {"league": 1, "season": season}
        if date:
            params["date"] = date
        
        try:
            resp = self.client.get(f"{self.base_url}/games", params=params)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("response", [])
        except Exception as e:
            logger.error(f"API-Sports get_games error: {e}")
        return []
    
    def get_teams(self, season: int = 2024) -> List[Dict]:
        """Get MLB teams"""
        try:
            resp = self.client.get(f"{self.base_url}/teams", params={"league": 1, "season": season})
            if resp.status_code == 200:
                return resp.json().get("response", [])
        except Exception as e:
            logger.error(f"API-Sports get_teams error: {e}")
        return []
    
    def parse_game(self, game: Dict) -> Dict:
        """Parse API-Sports game into standard format"""
        teams = game.get("teams", {})
        scores = game.get("scores", {})
        
        return {
            "game_id": game.get("id"),
            "date": game.get("date"),
            "timestamp": game.get("timestamp"),
            "status": game.get("status", {}).get("short", "?"),
            "home_team": {
                "id": teams.get("home", {}).get("id"),
                "name": teams.get("home", {}).get("name"),
                "logo": teams.get("home", {}).get("logo"),
            },
            "away_team": {
                "id": teams.get("away", {}).get("id"),
                "name": teams.get("away", {}).get("name"),
                "logo": teams.get("away", {}).get("logo"),
            },
            "scores": {
                "home": scores.get("home", {}).get("total", 0),
                "away": scores.get("away", {}).get("total", 0),
            },
            "innings": {
                "home": scores.get("home", {}).get("innings", {}),
                "away": scores.get("away", {}).get("innings", {}),
            },
            "hits_errors": {
                "home": {"hits": scores.get("home", {}).get("hits", 0), "errors": scores.get("home", {}).get("errors", 0)},
                "away": {"hits": scores.get("away", {}).get("hits", 0), "errors": scores.get("away", {}).get("errors", 0)},
            }
        }


class TheOddsAPIClient:
    """The Odds API for betting odds"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("ODDS_API_KEY")
        self.base_url = "https://api.the-odds-api.com/v4"
        self._client: Optional[httpx.Client] = None
    
    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                headers={"apikey": self.api_key},
                timeout=15
            )
        return self._client
    
    def close(self):
        if self._client:
            self._client.close()
            self._client = None
    
    def get_odds(self, sport: str = "baseball_mlb", regions: str = "us") -> Dict:
        """Get current odds for MLB"""
        if not self.api_key or self.api_key == "your-api-key-here":
            logger.warning("The Odds API key not configured")
            return {}
        
        try:
            resp = self.client.get(
                f"{self.base_url}/sports/{sport}/odds",
                params={"regions": regions, "markets": "h2h"}
            )
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 401:
                logger.error("The Odds API key is invalid")
                return {}
        except Exception as e:
            logger.error(f"The Odds API error: {e}")
        return {}
    
    def parse_odds(self, odds_data: Dict, home_team: str, away_team: str) -> Optional[Dict]:
        """Parse odds data into standard format"""
        if not odds_data or "data" not in odds_data:
            return None
        
        for event in odds_data.get("data", []):
            # Find matching game
            event_home = event.get("home_team", "")
            event_away = event.get("away_team", "")
            
            if home_team.lower() in event_home.lower() or event_home.lower() in home_team.lower():
                # Get best odds from bookmakers
                bookmakers = event.get("bookmakers", [])
                if not bookmakers:
                    continue
                
                best_home_odds = None
                best_away_odds = None
                
                for bm in bookmakers:
                    for market in bm.get("markets", []):
                        if market.get("key") != "h2h":
                            continue
                        for outcome in market.get("outcomes", []):
                            if outcome.get("name") == event_home:
                                best_home_odds = outcome.get("price")
                            elif outcome.get("name") == event_away:
                                best_away_odds = outcome.get("price")
                
                if best_home_odds and best_away_odds:
                    return {
                        "home_team": event_home,
                        "away_team": event_away,
                        "home_odds": best_home_odds,
                        "away_odds": best_away_odds,
                        "bookmaker": bookmakers[0].get("title") if bookmakers else "unknown"
                    }
        
        return None


class MultiSourceOddsAdapter:
    """
    Multi-source odds adapter with fallback logic:
    1. The Odds API (primary)
    2. API-Sports odds (fallback - may not be available on free plan)
    3. Realistic simulation (last resort for testing)
    """
    
    def __init__(self):
        self.the_odds = TheOddsAPIClient()
        self.simulator = None  # Will import from realistic_market
        
        # Check if The Odds API works
        self.odds_api_works = self._check_odds_api()
    
    def _check_odds_api(self) -> bool:
        """Check if The Odds API is working"""
        try:
            test = self.the_odds.get_odds()
            if test:
                logger.info("The Odds API is working")
                return True
        except:
            pass
        logger.warning("The Odds API not available")
        return False
    
    def get_odds(self, game_date: str, home_team: str, away_team: str, 
                 true_prob_home: float = None) -> Dict:
        """
        Get odds with multi-source fallback
        
        Returns:
            Dict with odds, or simulation if no real odds available
        """
        # Option 1: Try The Odds API
        if self.odds_api_works:
            try:
                odds_data = self.the_odds.get_odds()
                parsed = self.the_odds.parse_odds(odds_data, home_team, away_team)
                if parsed:
                    logger.info(f"Got real odds from The Odds API: {parsed}")
                    return {
                        "source": "the_odds_api",
                        "home_odds": parsed["home_odds"],
                        "away_odds": parsed["away_odds"],
                        "bookmaker": parsed["bookmaker"],
                        "type": "real"
                    }
            except Exception as e:
                logger.error(f"The Odds API failed: {e}")
        
        # Option 2: Use realistic simulation (fallback)
        if true_prob_home is not None:
            return self._simulate_odds(true_prob_home)
        
        # Option 3: Return placeholder (no odds available)
        return {
            "source": "none",
            "home_odds": None,
            "away_odds": None,
            "type": "unavailable"
        }
    
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
    
    def close(self):
        self.the_odds.close()


def test_mlb_integration():
    """Test the full MLB integration"""
    print("="*60)
    print("  MLB INTEGRATION TEST")
    print("="*60)
    
    # Test API-Sports (games/teams)
    print("\n[1] Testing API-Sports (games/teams)...")
    api_sports = APISportsMLBClient()
    games = api_sports.get_games(season=2024, limit=5)
    
    if games:
        print(f"  Got {len(games)} games")
        game = games[0]
        parsed = api_sports.parse_game(game)
        print(f"  Sample: {parsed['home_team']['name']} vs {parsed['away_team']['name']}")
        print(f"  Score: {parsed['scores']['home']} - {parsed['scores']['away']}")
    else:
        print("  No games returned")
    
    teams = api_sports.get_teams(season=2024)
    print(f"  Got {len(teams)} teams")
    
    api_sports.close()
    
    # Test The Odds API
    print("\n[2] Testing The Odds API...")
    odds_adapter = MultiSourceOddsAdapter()
    print(f"  The Odds API working: {odds_adapter.odds_api_works}")
    
    # Test simulation fallback
    print("\n[3] Testing simulation fallback...")
    sim_odds = odds_adapter.get_odds(
        game_date="2024-09-15",
        home_team="Yankees",
        away_team="Dodgers",
        true_prob_home=0.55
    )
    print(f"  Simulated odds: {sim_odds}")
    
    odds_adapter.close()
    
    print("\n" + "="*60)
    print("  INTEGRATION COMPLETE")
    print("="*60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_mlb_integration()
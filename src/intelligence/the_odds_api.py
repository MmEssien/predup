import sys
from pathlib import Path
_root = Path(r"C:\Users\Strategic Shelter\.antigravity\AI\PredUp")
sys.path.insert(0, str(_root))

import os
import httpx
import logging
from typing import Dict, List, Optional
from abc import ABC, abstractmethod
from dotenv import load_dotenv

load_dotenv(_root / ".env")
logger = logging.getLogger(__name__)


class TheOddsAPIProvider:
    """
    The Odds API provider for real betting odds.
    
    API Key format: apiKey (camelCase) as query parameter
    """
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("ODDS_API_KEY") or "dca7069462322213519c88f447526adc"
        self.base_url = "https://api.the-odds-api.com/v4"
        self._client = None
        self._checked = False
        self._available = False
        self._credits_remaining = None
    
    def is_available(self) -> bool:
        if not self._checked:
            self._check_availability()
        return self._available
    
    def _check_availability(self):
        """Check if The Odds API is working"""
        try:
            client = self._get_client()
            resp = client.get(f"{self.base_url}/sports", 
                          params={"apiKey": self.api_key})
            
            if resp.status_code == 200:
                self._available = True
                logger.info("The Odds API is working")
                
                # Check credits
                self._credits_remaining = resp.headers.get("X-odds-api-credits-remaining", "N/A")
                logger.info(f"Credits remaining: {self._credits_remaining}")
            else:
                self._available = False
                logger.warning(f"The Odds API error: {resp.status_code}")
            
        except Exception as e:
            logger.error(f"The Odds API check failed: {e}")
            self._available = False
        finally:
            self._checked = True
    
    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=15)
        return self._client
    
    def get_odds(self, sport: str = "baseball_mlb", regions: str = "us") -> Dict:
        """Get current odds for a sport"""
        if not self.is_available():
            return {}
        
        try:
            client = self._get_client()
            resp = client.get(
                f"{self.base_url}/sports/{sport}/odds",
                params={
                    "apiKey": self.api_key,
                    "regions": regions,
                    "markets": "h2h"
                }
            )
            
            if resp.status_code == 200:
                # Update credits
                self._credits_remaining = resp.headers.get("X-odds-api-credits-remaining")
                
                data = resp.json()
                return {"data": data, "count": len(data)}
            else:
                logger.error(f"Odds API error: {resp.status_code}")
                return {}
                
        except Exception as e:
            logger.error(f"Get odds error: {e}")
            return {}
    
    def parse_game_odds(self, odds_data: Dict, home_team: str, away_team: str) -> Optional[Dict]:
        """Parse odds for a specific game"""
        if not odds_data or "data" not in odds_data:
            return None
        
        data = odds_data.get("data", [])
        
        # Find matching game
        for event in data:
            event_home = event.get("home_team", "")
            event_away = event.get("away_team", "")
            
            # Try to match teams (case-insensitive partial match)
            home_match = home_team.lower() in event_home.lower() or event_home.lower() in home_team.lower()
            away_match = away_team.lower() in event_away.lower() or event_away.lower() in away_team.lower()
            
            if home_match and away_match:
                # Get best odds
                bookmakers = event.get("bookmakers", [])
                if not bookmakers:
                    continue
                
                best_home_odds = None
                best_away_odds = None
                best_bookmaker = None
                
                # Find best (highest) odds across bookmakers
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
                    return {
                        "home_team": event_home,
                        "away_team": event_away,
                        "home_odds": best_home_odds,
                        "away_odds": best_away_odds,
                        "bookmaker": best_bookmaker,
                        "source": "the_odds_api",
                        "type": "real"
                    }
        
        return None
    
    def close(self):
        if self._client:
            self._client.close()
            self._client = None


def test_the_odds_api():
    """Test The Odds API integration"""
    print("="*70)
    print("  THE ODDS API INTEGRATION TEST")
    print("="*70)
    
    provider = TheOddsAPIProvider()
    
    print("\n[1] Checking availability...")
    print(f"    Available: {provider.is_available()}")
    print(f"    Credits: {provider._credits_remaining}")
    
    if not provider.is_available():
        print("    The Odds API not available")
        return
    
    print("\n[2] Fetching MLB odds...")
    odds_data = provider.get_odds("baseball_mlb", "us")
    print(f"    Games returned: {odds_data.get('count', 0)}")
    
    if odds_data.get("data"):
        print("\n[3] Sample odds:")
        for game in odds_data["data"][:3]:
            home = game.get("home_team")
            away = game.get("away_team")
            
            bookmakers = game.get("bookmakers", [])
            if bookmakers:
                for bm in bookmakers[:1]:
                    for market in bm.get("markets", []):
                        if market.get("key") == "h2h":
                            print(f"\n    {home} vs {away}")
                            print(f"    Bookmaker: {bm.get('title')}")
                            for outcome in market.get("outcomes", []):
                                print(f"      {outcome.get('name')}: {outcome.get('price')}")
    
    print("\n" + "="*70)
    provider.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_the_odds_api()
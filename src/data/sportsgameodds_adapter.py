"""
SportsGameOdds Adapter - PRIMARY Odds Source
Fetches real-time bookmaker odds for Football, MLB, NBA
"""

import os
import logging
from datetime import datetime
from typing import Dict, List, Optional

import httpx

from dotenv import load_dotenv
load_dotenv(override=False)

logger = logging.getLogger(__name__)


class SportsGameOddsAdapter:
    """
    Primary odds adapter using SportsGameOdds API.
    Responsibilities:
    - Fetch real-time bookmaker odds
    - Coverage: Football, MLB, NBA
    - Cache: 2-10 min TTL
    - Return unified schema with source="sportsgameodds"
    """
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("SPORTSGAMEODDS_KEY", "")
        self.base_url = os.getenv("SPORTSGAMEODDS_URL", "https://api.sportsgameodds.com/v2")
        self.timeout = 5  # FAIL FAST - 5 second max
        self._client: Optional[httpx.Client] = None
        
        # Rate limiting
        self._last_request = None
        self._min_request_interval = 1.0  # seconds
        
        # Stats
        self._requests = 0
        self._success = 0
        self._failed = 0
    
    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                headers={"Accept": "application/json"},
                timeout=self.timeout
            )
        return self._client
    
    def close(self):
        """Close HTTP client"""
        if self._client:
            self._client.close()
            self._client = None
    
    def get_odds(
        self, 
        sport: str, 
        home_team: str, 
        away_team: str,
        league: str = None,
        use_cache: bool = True
    ) -> Optional[Dict]:
        """
        Fetch odds for a fixture.
        
        Args:
            sport: football, mlb, nba
            home_team: Home team name
            away_team: Away team name  
            league: Optional league filter
            use_cache: Whether to use cached odds
        
        Returns:
            Dict with unified odds schema or None if unavailable
        """
        from src.data.odds_cache import get_odds_cache
        cache = get_odds_cache()
        
        # Build cache key
        cache_key = f"{sport}_{home_team}_{away_team}"
        
        # Check cache first
        if use_cache:
            cached = cache.get(cache_key, "sportsgameodds")
            if cached:
                logger.debug(f"[SPORTSGAMEODDS] Cache hit: {home_team} vs {away_team}")
                return cached
        
        self._requests += 1
        
        # Build API request - use /events endpoint
        try:
            response = self.client.get(
                f"{self.base_url}/events",
                params={
                    "apiKey": self.api_key,
                    "leagueID": self._map_league(sport),
                    "oddsAvailable": "true",
                    "limit": 50
                }
            )
            response.raise_for_status()
            
            data = response.json()
            
            # Normalize response
            odds_data = self._normalize_response(data, sport, home_team, away_team)
            
            if odds_data:
                self._success += 1
                # Cache the result
                cache.set(cache_key, odds_data, "sportsgameodds")
                logger.info(f"[SPORTSGAMEODDS] SUCCESS: {home_team} vs {away_team} | "
                           f"Home: {odds_data.get('home_odds'):.2f} | "
                           f"Away: {odds_data.get('away_odds'):.2f} | "
                           f"Source: {odds_data.get('source')}")
            else:
                self._failed += 1
                logger.warning(f"[SPORTSGAMEODDS] No odds returned: {home_team} vs {away_team}")
            
            return odds_data
            
        except httpx.HTTPStatusError as e:
            self._failed += 1
            logger.warning(f"[SPORTSGAMEODDS] HTTP {e.response.status_code}: {home_team} vs {away_team}")
            return None
        except httpx.RequestError as e:
            self._failed += 1
            logger.warning(f"[SPORTSGAMEODDS] Request failed: {e}")
            return None
        except Exception as e:
            self._failed += 1
            logger.error(f"[SPORTSGAMEODDS] Error: {e}")
            return None
    
    def get_odds_batch(
        self, 
        sport: str, 
        fixtures: List[Dict],
        use_cache: bool = True
    ) -> List[Dict]:
        """
        Fetch odds for multiple fixtures efficiently.
        
        Args:
            sport: football, mlb, nba
            fixtures: List of {home_team, away_team, fixture_id}
            use_cache: Whether to use cached odds
        
        Returns:
            List of normalized odds data
        """
        results = []
        
        for fixture in fixtures[:20]:  # Limit batch size
            home = fixture.get("home_team", "")
            away = fixture.get("away_team", "")
            fixture_id = fixture.get("fixture_id", "")
            
            odds = self.get_odds(sport, home, away, use_cache=use_cache)
            
            if odds:
                odds["fixture_id"] = fixture_id
                results.append(odds)
        
        logger.info(f"[SPORTSGAMEODDS] Batch: {len(results)}/{len(fixtures)} odds fetched")
        return results
    
    def _normalize_response(self, raw: Dict, sport: str, home: str, away: str) -> Optional[Dict]:
        """Normalize SportsGameOdds response to unified schema"""
        if not raw:
            return None
        
        # Events endpoint returns {"success": true, "data": [...]}
        events = raw.get("data", [])
        
        # Find matching event by team names
        matching_event = None
        for event in events:
            event_home = event.get("teams", {}).get("home", {}).get("names", {}).get("long", "").lower()
            event_away = event.get("teams", {}).get("away", {}).get("names", {}).get("long", "").lower()
            
            if (home.lower() in event_home or event_home in home.lower()) and \
               (away.lower() in event_away or event_away in away.lower()):
                matching_event = event
                break
        
        if not matching_event:
            return None
        
        # Extract odds from event
        odds_obj = matching_event.get("odds", {})
        
        # Find moneyline odds (h2h equivalent) - look for patterns like:
        # "winner-home-game-h2h-home" or "moneyline-home-game-h2h-home"
        home_odds = None
        away_odds = None
        
        for odd_id, odd_data in odds_obj.items():
            if "h2h" in odd_id.lower() and "home" in odd_id.lower():
                home_odds = odd_data.get("bookOdds") or odd_data.get("fairOdds")
            elif "h2h" in odd_id.lower() and "away" in odd_id.lower():
                away_odds = odd_data.get("bookOdds") or odd_data.get("fairOdds")
        
        # Convert American odds to decimal
        def american_to_decimal(am_odds):
            if not am_odds:
                return None
            try:
                am = int(am_odds.replace("+", ""))
                if am > 0:
                    return round(1 + (am / 100), 2)
                else:
                    return round(1 + (100 / abs(am)), 2)
            except:
                return None
        
        home_decimal = american_to_decimal(home_odds)
        away_decimal = american_to_decimal(away_odds)
        
        if not home_decimal or not away_decimal:
            return None
        
        return {
            "sport": sport,
            "fixture_id": matching_event.get("eventID", ""),
            "home_team": home,
            "away_team": away,
            "home_odds": home_decimal,
            "away_odds": away_decimal,
            "draw_odds": None,
            "overround": None,
            "timestamp": datetime.now().isoformat(),
            "source": "sportsgameodds",
            "confidence": 0.9,
            "cache_status": "fresh"
        }
    
    def _map_league(self, sport: str) -> str:
        """Map sport to league ID for API"""
        mapping = {
            "nba": "NBA",
            "mlb": "MLB",
            "nfl": "NFL",
            "football": "EPL"
        }
        return mapping.get(sport.lower(), "NBA")
    
    def is_available(self) -> bool:
        """Check if API is accessible"""
        if not self.api_key:
            return False
        
        try:
            response = self.client.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def get_stats(self) -> Dict:
        """Get adapter usage statistics"""
        return {
            "adapter": "sportsgameodds",
            "requests": self._requests,
            "success": self._success,
            "failed": self._failed,
            "success_rate": self._success / self._requests if self._requests > 0 else 0,
            "is_available": self.is_available()
        }


def test_sportsgameodds():
    """Test SportsGameOdds adapter"""
    print("Testing SportsGameOdds Adapter...")
    
    adapter = SportsGameOddsAdapter()
    
    print(f"\n1. Availability check: {adapter.is_available()}")
    
    # Test Football odds
    print("\n2. Testing Football odds...")
    odds = adapter.get_odds("football", "Arsenal", "Liverpool")
    print(f"   Result: {odds}")
    
    # Test MLB odds
    print("\n3. Testing MLB odds...")
    odds = adapter.get_odds("mlb", "Yankees", "Dodgers")
    print(f"   Result: {odds}")
    
    # Test NBA odds
    print("\n4. Testing NBA odds...")
    odds = adapter.get_odds("nba", "Lakers", "Celtics")
    print(f"   Result: {odds}")
    
    # Stats
    print("\n5. Adapter stats:")
    print(f"   {adapter.get_stats()}")
    
    # Cache stats
    from src.data.odds_cache import get_odds_cache
    print(f"\n6. Cache stats:")
    print(f"   {get_odds_cache().get_stats()}")
    
    adapter.close()
    print("\nTest complete.")


if __name__ == "__main__":
    test_sportsgameodds()
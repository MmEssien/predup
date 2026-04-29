"""Odds API Client using the-odds-api.com - Optimized for 500 credits/month"""

import os
import time
import json
from typing import Optional, List, Dict
from datetime import datetime, timedelta
from pathlib import Path
import httpx
import logging

logger = logging.getLogger(__name__)

SPORTS = [
    "soccer_england_premier_league", 
    "soccer_germany_bundesliga",
    "soccer_spain_la_liga", 
    "soccer_italy_serie_a",
    "soccer_france_ligue_1", 
    "basketball_nba",  # NBA support added
]

CACHE_DIR = Path(".cache")
CACHE_DIR.mkdir(exist_ok=True)


class OddsCache:
    """Smart caching for odds data"""
    
    def __init__(self, ttl_minutes: int = 60):
        self.ttl = timedelta(minutes=ttl_minutes)
        self._memory = {}
    
    def get(self, key: str) -> Optional[Dict]:
        if key in self._memory:
            cached_time, data = self._memory[key]
            if datetime.now() - cached_time < self.ttl:
                return data
        return None
    
    def set(self, key: str, data: Dict) -> None:
        self._memory[key] = (datetime.now(), data)
    
    def save_to_disk(self, key: str) -> None:
        if key in self._memory:
            path = CACHE_DIR / f"odds_{key.replace('/', '_')}.json"
            with open(path, "w") as f:
                json.dump({"data": self._memory[key][1], "time": datetime.now().isoformat()}, f)
    
    def load_from_disk(self, key: str) -> Optional[Dict]:
        path = CACHE_DIR / f"odds_{key.replace('/', '_')}.json"
        if path.exists():
            try:
                with open(path, "r") as f:
                    return json.load(f).get("data")
            except:
                pass
        return None


class OddsAPIClient:
    """Client for the-odds-api.com - Ultra-optimized for 500 credits/month"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ODDS_API_KEY")
        self.base_url = "https://api.the-odds-api.com/v4"
        self.timeout = 15
        self._client: Optional[httpx.Client] = None
        self.cache = OddsCache(ttl_minutes=60)
        self._credits_used = 0
        self._credits_remaining: Optional[int] = None
        
        # Only fetch active Odds API if key provided
        self._enabled = bool(self.api_key and self.api_key != "your-api-key-here")

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                headers={"apikey": self.api_key},
                timeout=self.timeout
            )
        return self._client

    def close(self):
        if self._client:
            self._client.close()
            self._client = None

    @property
    def credits_remaining(self) -> Optional[int]:
        """Get remaining credits - only check once per session"""
        if self._credits_remaining is None and self._enabled:
            try:
                response = self.client.get(f"{self.base_url}/sports")
                self._credits_remaining = int(response.headers.get("X-odds-api-credits-remaining", 0))
                logger.info(f"Odds API credits remaining: {self._credits_remaining}")
            except Exception as e:
                logger.warning(f"Could not check credits: {e}")
                # Treat as enabled even if we can't check - try fetching anyway
                self._credits_remaining = 100
        return self._credits_remaining

    def is_available(self) -> bool:
        """Check if Odds API is available - try fetching even with low credits"""
        if not self._enabled:
            return False
        # Always try - API might work even if credits report weird
        return True

    def get_odds(self, sport: str = "soccer_england_premier_league",
                 regions: str = "eu", markets: str = "h2h",
                 force_refresh: bool = False) -> Optional[Dict]:
        """Fetch current odds - uses 1 credit per call, caches for 1 hour"""
        
        if not self.is_available():
            cached = self.cache.get(sport)
            if cached:
                logger.info(f"Using cached odds for {sport}")
                return cached
            
            # Try loading from disk
            cached = self.cache.load_from_disk(sport)
            if cached:
                logger.info(f"Using disk-cached odds for {sport}")
                return cached
                
            logger.warning(f"Odds API not available and no cache for {sport}")
            return None

        cache_key = f"{sport}:{regions}:{markets}"
        
        # Use cache unless force refresh
        if not force_refresh:
            cached = self.cache.get(cache_key)
            if cached:
                logger.debug(f"Using in-memory cache for {sport}")
                return cached

        # Check credits before making request
        if self.credits_remaining is not None and self.credits_remaining <= 0:
            logger.error("No Odds API credits remaining")
            return self.cache.get(cache_key)

        try:
            response = self.client.get(
                f"{self.base_url}/sports/{sport}/odds",
                params={"regions": regions, "markets": markets}
            )
            response.raise_for_status()

            data = response.json()
            
            # Cache the result
            self.cache.set(cache_key, data)
            self.cache.save_to_disk(cache_key)
            
            self._credits_used += 1
            remaining = response.headers.get("X-odds-api-credits-remaining")
            if remaining:
                self._credits_remaining = int(remaining)
                
            logger.info(f"Fetched odds for {sport} - credits remaining: {remaining}")
            return data
            
        except Exception as e:
            logger.error(f"Failed to fetch odds for {sport}: {e}")
            # Return cached if available
            return self.cache.get(cache_key)

    def get_odds_batch(self, sports: Optional[List[str]] = None) -> Dict[str, Optional[Dict]]:
        """Fetch odds efficiently for multiple sports"""
        if sports is None:
            sports = SPORTS

        all_odds = {}
        for sport in sports[:3]:  # Limit to top 3 leagues
            all_odds[sport] = self.get_odds(sport)
            
        return all_odds

    def get_h2h_odds_for_fixture(self, fixture_id: str, sport: str) -> Optional[Dict]:
        """Get odds for specific fixture - most efficient approach"""
        # This is more targeted than fetching all odds
        odds = self.get_odds(sport)
        if not odds or "data" not in odds:
            return None
            
        for event in odds.get("data", []):
            if event.get("id") == fixture_id:
                return event
        return None

    def get_upcoming(self, sport: str = "soccer_england_premier_league",
                     days_ahead: int = 1) -> Optional[Dict]:
        """Get upcoming events efficiently - cheaper than full odds fetch"""
        if not self.is_available():
            return None
            
        try:
            from_dt = datetime.now()
            to_dt = from_dt + timedelta(days=days_ahead)
            
            response = self.client.get(
                f"{self.base_url}/sports/{sport}/events",
                params={
                    "dateFormat": "iso",
                    "commenceTimeFrom": from_dt.isoformat(),
                    "commenceTimeTo": to_dt.isoformat()
                }
            )
            response.raise_for_status()
            
            self._credits_used += 1
            remaining = response.headers.get("X-odds-api-credits-remaining")
            if remaining:
                self._credits_remaining = int(remaining)
                
            return response.json()
        except Exception as e:
            logger.warning(f"Failed to get upcoming events: {e}")
            return None

    def get_credits_info(self) -> Dict:
        """Get credits usage info"""
        return {
            "enabled": self._enabled,
            "credits_used": self._credits_used,
            "credits_remaining": self.credits_remaining,
            "can_fetch": self.is_available()
        }

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_ttl):
        self.close()
"""API Client for Football Data Providers - Optimized with caching"""

import os
import json
import time
from typing import Optional, Any
from pathlib import Path
from datetime import datetime, timedelta
import httpx
import logging

logger = logging.getLogger(__name__)


class CacheManager:
    """File-based cache with TTL for API responses"""
    
    def __init__(self, cache_dir: str = ".cache", default_ttl_seconds: int = 3600):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.default_ttl = default_ttl_seconds
        self._memory_cache = {}
    
    def _get_cache_path(self, key: str) -> Path:
        safe_key = key.replace("/", "_").replace(":", "_").replace("?", "_")
        return self.cache_dir / f"{safe_key}.json"
    
    def get(self, key: str) -> Optional[Any]:
        # Check memory cache first
        if key in self._memory_cache:
            cached_time, data = self._memory_cache[key]
            if time.time() - cached_time < self.default_ttl:
                logger.debug(f"Memory cache hit: {key}")
                return data
        
        # Check file cache
        cache_path = self._get_cache_path(key)
        if cache_path.exists():
            try:
                with open(cache_path, "r") as f:
                    cache_data = json.load(f)
                
                cached_at = cache_data.get("cached_at", 0)
                if time.time() - cached_at < self.default_ttl:
                    logger.debug(f"File cache hit: {key}")
                    self._memory_cache[key] = (time.time(), cache_data["data"])
                    return cache_data["data"]
                else:
                    cache_path.unlink()  # Expired
            except Exception as e:
                logger.warning(f"Cache read error: {e}")
        
        return None
    
    def set(self, key: str, data: Any, ttl: Optional[int] = None) -> None:
        # Memory cache
        self._memory_cache[key] = (time.time(), data)
        
        # File cache
        ttl = ttl or self.default_ttl
        cache_path = self._get_cache_path(key)
        cache_data = {
            "data": data,
            "cached_at": time.time(),
            "ttl": ttl
        }
        try:
            with open(cache_path, "w") as f:
                json.dump(cache_data, f)
        except Exception as e:
            logger.warning(f"Cache write error: {e}")
    
    def clear(self) -> None:
        """Clear all cache"""
        self._memory_cache.clear()
        for f in self.cache_dir.glob("*.json"):
            f.unlink()


_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager


class FootballAPIClient:
    """Client for API-Football (football-data.org) - Optimized"""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or os.getenv("FOOTBALL_DATA_KEY") or os.getenv("API_FOOTBALL_DATA_KEY") or os.getenv("API_FOOTBALL_API_KEY")
        self.base_url = base_url or os.getenv(
            "FOOTBALL_DATA_URL",
            "https://api.football-data.org/v4"
        )
        self.timeout = 30
        self._client: Optional[httpx.Client] = None
        self.cache = get_cache_manager()
        self._rate_limit_delay = 0.5  # 2 requests per second max
        self._last_request_time = 0

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                headers={
                    "X-Auth-Token": self.api_key,
                    "Content-Type": "application/json"
                },
                timeout=self.timeout
            )
        return self._client

    def close(self):
        if self._client:
            self._client.close()
            self._client = None

    def _throttle(self) -> None:
        """Rate limiting - respect API limits"""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._rate_limit_delay:
            time.sleep(self._rate_limit_delay - elapsed)
        self._last_request_time = time.time()

    def _cached_request(self, url: str, params: dict = None, cache_ttl: int = 3600) -> dict:
        """Make request with caching - minimizes API calls"""
        cache_key = f"{url}:{json.dumps(params or {}, sort_keys=True)}"
        
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        
        self._throttle()
        response = self.client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        self.cache.set(cache_key, data, cache_ttl)
        return data

    def get_competitions(self, use_cache: bool = True) -> dict:
        """Fetch available competitions - cached for 24 hours"""
        cache_ttl = 86400 if use_cache else 0
        return self._cached_request(
            f"{self.base_url}/competitions",
            cache_ttl=cache_ttl
        )

    def get_competition_matches(self, competition_code: str, season: int, use_cache: bool = True) -> dict:
        """Fetch matches for a competition/season - cached for 1 hour"""
        cache_ttl = 3600 if use_cache else 0
        return self._cached_request(
            f"{self.base_url}/competitions/{competition_code}/matches",
            params={"season": season, "limit": 500},
            cache_ttl=cache_ttl
        )

    def get_match(self, match_id: int, use_cache: bool = True) -> dict:
        """Fetch specific match details - cache for 30 min"""
        cache_ttl = 1800 if use_cache else 0
        return self._cached_request(
            f"{self.base_url}/matches/{match_id}",
            cache_ttl=cache_ttl
        )

    def get_team(self, team_id: int, use_cache: bool = True) -> dict:
        """Fetch team details - cache for 24 hours"""
        cache_ttl = 86400 if use_cache else 0
        return self._cached_request(
            f"{self.base_url}/teams/{team_id}",
            cache_ttl=cache_ttl
        )

    def get_matches_by_date(self, date: str, use_cache: bool = True) -> dict:
        """Fetch matches for a specific date - cache for 1 hour"""
        return self._get_matches(date=date, use_cache=use_cache)

    def get_matches(self, competition_code: str = None, date: str = None, use_cache: bool = True) -> dict:
        """General matches endpoint"""
        return self._get_matches(competition_code, date, use_cache)

    def _get_matches(self, competition_code: str = None, date: str = None, use_cache: bool = True) -> dict:
        """Internal method for fetching matches with optional caching"""
        params = {}
        if competition_code:
            params["competitionCode"] = competition_code
        if date:
            params["date"] = date
        
        cache_ttl = 3600 if use_cache else 0
        return self._cached_request(
            f"{self.base_url}/matches",
            params=params if params else None,
            cache_ttl=cache_ttl
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
"""
Odds API Adapter - SECONDARY Odds Source (Quota-Controlled)
The Odds API with strict credit tracking and quota management
"""

import os
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import httpx

from dotenv import load_dotenv
load_dotenv(override=False)

logger = logging.getLogger(__name__)

# Constants
MONTHLY_CREDIT_LIMIT = 500
DAILY_WARNING_THRESHOLD = 50  # Warn when less than 50 credits left

CACHE_DIR = Path(".cache")
CACHE_DIR.mkdir(exist_ok=True)


class OddsAPIQuotaTracker:
    """
    Tracks The Odds API credit usage.
    Responsibilities:
    - Daily and monthly consumption tracking
    - Block low-value requests when quota low
    - Persist usage across sessions
    """
    
    def __init__(self):
        self.usage_file = CACHE_DIR / "oddsapi_usage.json"
        self._load_usage()
    
    def _load_usage(self):
        """Load usage from disk"""
        if self.usage_file.exists():
            try:
                with open(self.usage_file, 'r') as f:
                    self.data = json.load(f)
            except:
                self._reset_usage()
        else:
            self._reset_usage()
    
    def _reset_usage(self):
        """Initialize usage tracking"""
        self.data = {
            "daily": {
                "used": 0,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "requests": []
            },
            "monthly": {
                "used": 0,
                "year_month": datetime.now().strftime("%Y-%m"),
                "requests": []
            }
        }
    
    def _save_usage(self):
        """Save usage to disk"""
        with open(self.usage_file, 'w') as f:
            json.dump(self.data, f, indent=2, default=str)
    
    def _check_and_reset(self):
        """Check if new day/month and reset if needed"""
        today = datetime.now().strftime("%Y-%m-%d")
        year_month = datetime.now().strftime("%Y-%m")
        
        # Daily reset
        if self.data["daily"]["date"] != today:
            self.data["daily"]["used"] = 0
            self.data["daily"]["date"] = today
            self.data["daily"]["requests"] = []
        
        # Monthly reset
        if self.data["monthly"]["year_month"] != year_month:
            self.data["monthly"]["used"] = 0
            self.data["monthly"]["year_month"] = year_month
            self.data["monthly"]["requests"] = []
        
        self._save_usage()
    
    def can_request(self) -> bool:
        """Check if credits available"""
        self._check_and_reset()
        
        daily_left = 100 - self.data["daily"]["used"]  # Assume ~100/day max
        monthly_left = MONTHLY_CREDIT_LIMIT - self.data["monthly"]["used"]
        
        return daily_left > 5 and monthly_left > 5
    
    def get_daily_credits_left(self) -> int:
        """Get daily credits remaining"""
        self._check_and_reset()
        return max(0, 100 - self.data["daily"]["used"])
    
    def get_monthly_credits_left(self) -> int:
        """Get monthly credits remaining"""
        self._check_and_reset()
        return max(0, MONTHLY_CREDIT_LIMIT - self.data["monthly"]["used"])
    
    def record_request(self, credits: int = 1):
        """Record a credit usage"""
        self._check_and_reset()
        
        now = datetime.now().isoformat()
        
        self.data["daily"]["used"] += credits
        self.data["daily"]["requests"].append(now)
        self.data["monthly"]["used"] += credits
        self.data["monthly"]["requests"].append(now)
        
        self._save_usage()
    
    def get_stats(self) -> Dict:
        """Get quota usage statistics"""
        self._check_and_reset()
        return {
            "daily_used": self.data["daily"]["used"],
            "daily_left": self.get_daily_credits_left(),
            "monthly_used": self.data["monthly"]["used"],
            "monthly_left": self.get_monthly_credits_left(),
            "monthly_limit": MONTHLY_CREDIT_LIMIT,
            "can_request": self.can_request()
        }


class OddsAPIAdapter:
    """
    Secondary odds adapter using The Odds API.
    Responsibilities:
    - Quota-controlled usage (500 credits/month)
    - Aggressive caching (30-60 min)
    - Graceful degradation when quota low
    """
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("ODDS_API_KEY", "")
        self.base_url = "https://api.the-odds-api.com/v4"
        self.timeout = 15
        self._client: Optional[httpx.Client] = None
        
        # Quota tracker
        self.quota = OddsAPIQuotaTracker()
        
        # Stats
        self._requests = 0
        self._success = 0
        self._skipped_quota = 0
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
        regions: str = "us,eu,uk",
        markets: str = "h2h",
        use_cache: bool = True,
        force_refresh: bool = False
    ) -> Optional[Dict]:
        """
        Fetch odds for a fixture.
        
        Args:
            sport: Sport key (e.g., "soccer_england_premier_league", "basketball_nba")
            home_team: Home team name
            away_team: Away team name
            regions: comma-separated region codes
            markets: bet market type
            use_cache: Whether to use cache
            force_refresh: Force refresh (overrides use_cache)
        
        Returns:
            Dict with unified odds schema or None if unavailable
        """
        from src.data.odds_cache import get_odds_cache
        cache = get_odds_cache()
        
        # Check quota first
        if not self.quota.can_request():
            self._skipped_quota += 1
            logger.warning("[ODDSAPI] Quota exhausted - skipping request")
            return None
        
        # Build cache key
        sport_key = self._map_sport(sport)
        cache_key = f"oddsapi_{sport_key}_{home_team}_{away_team}"
        
        # Check cache first
        if use_cache and not force_refresh:
            cached = cache.get(cache_key, "oddsapi")
            if cached:
                logger.debug(f"[ODDSAPI] Cache hit: {home_team} vs {away_team}")
                return cached
        
        self._requests += 1
        
        # Make API request
        try:
            response = self.client.get(
                f"{self.base_url}/sports/{sport_key}/odds",
                params={
                    "apiKey": self.api_key,
                    "regions": regions,
                    "markets": markets
                }
            )
            response.raise_for_status()
            
            # Get remaining credits from header
            remaining = response.headers.get("X-odds-api-credits-remaining")
            if remaining:
                # Record usage
                self.quota.record_request(1)
            
            data = response.json()
            
            # Find matching fixture
            odds_data = self._find_fixture_odds(
                data, home_team, away_team, sport_key
            )
            
            if odds_data:
                self._success += 1
                cache.set(cache_key, odds_data, "oddsapi")
                logger.info(f"[ODDSAPI] SUCCESS: {home_team} vs {away_team} | "
                           f"Home: {odds_data.get('home_odds'):.2f} | "
                           f"Away: {odds_data.get('away_odds'):.2f}")
            else:
                self._failed += 1
                logger.warning(f"[ODDSAPI] No odds found: {home_team} vs {away_team}")
            
            return odds_data
            
        except httpx.HTTPStatusError as e:
            self._failed += 1
            logger.warning(f"[ODDSAPI] HTTP {e.response.status_code}: {home_team} vs {away_team}")
            return None
        except Exception as e:
            self._failed += 1
            logger.warning(f"[ODDSAPI] Error: {e}")
            return None
    
    def _map_sport(self, sport: str) -> str:
        """Map internal sport to Odds API sport key"""
        mapping = {
            "football": "soccer_epl",
            "mlb": "baseball_mlb", 
            "nba": "basketball_nba"
        }
        return mapping.get(sport, f"soccer_{sport}")
    
    def _find_fixture_odds(
        self, 
        data: Dict, 
        home: str, 
        away: str,
        sport: str
    ) -> Optional[Dict]:
        """Find odds for specific fixture from response"""
        # Handle both list and dict responses
        events = data.get("data", []) if isinstance(data, dict) else data
        
        for event in events:
            home_team = event.get("home_team", "").lower()
            away_team = event.get("away_team", "").lower()
            
            # Match teams
            if (home.lower() in home_team or home_team in home.lower()) and \
               (away.lower() in away_team or away_team in away.lower()):
                
                # Extract odds from first bookmaker
                bookmakers = event.get("bookmakers", [])
                if not bookmakers:
                    continue
                
                bm = bookmakers[0]
                
                # Markets is a list, find h2h market
                h2h_outcomes = []
                for m in bm.get("markets", []):
                    if m.get("key") == "h2h":
                        h2h_outcomes = m.get("outcomes", [])
                        break
                
                home_odds = None
                away_odds = None
                
                for outcome in h2h_outcomes:
                    name = outcome.get("name", "").lower()
                    if home.lower() in name or name in home.lower():
                        home_odds = outcome.get("price")
                    elif away.lower() in name or name in away.lower():
                        away_odds = outcome.get("price")
                
                if home_odds and away_odds:
                    # Calculate overround
                    implied_home = 1 / home_odds
                    implied_away = 1 / away_odds
                    total = implied_home + implied_away
                    overround = (total - 1) * 100
                    
                    return {
                        "sport": sport,
                        "fixture_id": event.get("id", ""),
                        "home_team": home,
                        "away_team": away,
                        "home_odds": float(home_odds),
                        "away_odds": float(away_odds),
                        "draw_odds": None,
                        "overround": overround,
                        "timestamp": datetime.now().isoformat(),
                        "source": "oddsapi",
                        "confidence": 0.7,  # Medium confidence for secondary
                        "cache_status": "fresh"
                    }
        
        return None
    
    def get_credits_info(self) -> Dict:
        """Get credit usage information"""
        return {
            "adapter": "oddsapi",
            "quota": self.quota.get_stats(),
            "requests": self._requests,
            "success": self._success,
            "skipped_quota": self._skipped_quota,
            "failed": self._failed
        }


def test_oddsapi():
    """Test Odds API adapter"""
    print("Testing Odds API Adapter...")
    
    adapter = OddsAPIAdapter()
    
    # Check quota
    print(f"\n1. Quota status: {adapter.quota.get_stats()}")
    
    # Test Football odds
    print("\n2. Testing Football odds...")
    odds = adapter.get_odds("football", "Arsenal", "Liverpool")
    print(f"   Result: {odds}")
    
    # Test NBA odds
    print("\n3. Testing NBA odds...")
    odds = adapter.get_odds("nba", "Lakers", "Celtics")
    print(f"   Result: {odds}")
    
    # Get stats
    print("\n4. Adapter stats:")
    print(adapter.get_credits_info())
    
    # Cache stats
    from src.data.odds_cache import get_odds_cache
    print(f"\n5. Cache stats:")
    print(get_odds_cache().get_stats())
    
    adapter.close()
    print("\nTest complete.")


if __name__ == "__main__":
    test_oddsapi()
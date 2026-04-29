"""
Unified Odds Adapter
STRICT mode - NO simulation, NO fallback generators
If odds missing = SKIP prediction
"""

import os
import logging
from typing import Dict, Optional
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class UnifiedOddsAdapter:
    """Strict odds adapter - real odds ONLY"""
    
    def __init__(self, api_key: Optional[str] = None, strict_mode: bool = True):
        self.api_key = api_key or os.getenv("ODDS_API_KEY", "")
        self.strict_mode = strict_mode
        self._adapters = {}
        self._cache = {}
        
        # Logging
        self._odds_requests = 0
        self._odds_success = 0
        self._odds_failed = 0
        self._skipped_games = []
    
    def get_odds(self, home_team: str, away_team: str, sport: str = None) -> Optional[Dict]:
        """Get odds - STRICT: real odds ONLY or FAIL"""
        self._odds_requests += 1
        
        if not sport:
            sport = self._detect_sport(home_team, away_team)
        
        if sport == "football":
            odds = self._get_football_odds(home_team, away_team)
        elif sport == "mlb":
            odds = self._get_mlb_odds(home_team, away_team)
        elif sport == "nba":
            odds = self._get_nba_odds(home_team, away_team)
        else:
            odds = None
        
        if odds and odds.get("home_odds"):
            self._odds_success += 1
            logger.info(f"[ODDS] {sport}: {home_team} vs {away_team} | {odds.get('home_odds'):.2f}/{odds.get('away_odds'):.2f} | SOURCE: API")
            return odds
        else:
            self._odds_failed += 1
            self._skipped_games.append({
                "home": home_team,
                "away": away_team,
                "sport": sport,
                "reason": "odds_unavailable"
            })
            logger.warning(f"[ODDS] {sport}: {home_team} vs {away_team} | STATUS: FAILED | ACTION: SKIP")
            return None
    
    def _detect_sport(self, home: str, away: str) -> str:
        """Detect sport from team names"""
        nba_teams = ["Lakers", "Warriors", "Celtics", "Heat", "Bulls", "Knicks", "Spurs", "Nets", "Bucks", "Suns"]
        for t in nba_teams:
            if t.lower() in home.lower() or t.lower() in away.lower():
                return "nba"
        
        mlb_teams = ["Yankees", "Dodgers", "Red Sox", "Cubs", "Giants", "Mets", "Rangers", "Astros", "Braves", "Phillies"]
        for t in mlb_teams:
            if t.lower() in home.lower() or t.lower() in away.lower():
                return "mlb"
        
        return "football"
    
    def _get_football_odds(self, home: str, away: str) -> Optional[Dict]:
        """Get football odds from API ONLY"""
        try:
            from src.data.football_odds_adapter import FootballOddsAdapter
            
            if "football" not in self._adapters:
                self._adapters["football"] = FootballOddsAdapter(self.api_key)
            
            return self._adapters["football"].get_odds(home, away)
        except ImportError:
            return None
        except Exception as e:
            logger.warning(f"Football odds API error: {e}")
            return None
    
    def _get_mlb_odds(self, home: str, away: str) -> Optional[Dict]:
        """Get MLB odds from API ONLY"""
        try:
            from src.data.mlb_odds_adapter import MultiSourceOddsAdapter
            
            if "mlb" not in self._adapters:
                self._adapters["mlb"] = MultiSourceOddsAdapter()
            
            return self._adapters["mlb"].get_odds("", home, away)
        except ImportError:
            return None
        except Exception as e:
            logger.warning(f"MLB odds API error: {e}")
            return None
    
    def _get_nba_odds(self, home: str, away: str) -> Optional[Dict]:
        """Get NBA odds from API ONLY"""
        try:
            from src.data.nba_odds_adapter import NBAOddsAdapter
            
            if "nba" not in self._adapters:
                self._adapters["nba"] = NBAOddsAdapter(self.api_key)
            
            return self._adapters["nba"].get_odds(home, away)
        except ImportError:
            return None
        except Exception as e:
            logger.warning(f"NBA odds API error: {e}")
            return None
    
    def get_stats(self) -> Dict:
        """Get odds adapter statistics"""
        return {
            "total_requests": self._odds_requests,
            "success": self._odds_success,
            "failed": self._odds_failed,
            "success_rate": self._odds_success / self._odds_requests if self._odds_requests > 0 else 0,
            "skipped_games": self._skipped_games
        }
    
    def close(self):
        """Close all adapters"""
        for adapter in self._adapters.values():
            if hasattr(adapter, "close"):
                adapter.close()
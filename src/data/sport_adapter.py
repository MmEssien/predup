"""
Unified Sport Adapter Interface
All sport clients implement this interface for consistency
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from datetime import datetime


class BaseSportAdapter(ABC):
    """Base class for all sport adapters"""
    
    sport_name: str = ""
    league_name: str = ""
    
    @abstractmethod
    def get_fixtures(self, date: Optional[str] = None, days_ahead: int = 1) -> List[Dict]:
        """Get upcoming fixtures/games"""
        pass
    
    @abstractmethod
    def get_live_games(self) -> List[Dict]:
        """Get currently live games"""
        pass
    
    @abstractmethod
    def get_team_stats(self, team_id: int) -> Dict:
        """Get team statistics"""
        pass
    
    @abstractmethod
    def get_odds(self, event_id: str, market: str = "moneyline") -> Dict:
        """Get betting odds for an event"""
        pass
    
    @abstractmethod
    def get_game_details(self, event_id: str) -> Dict:
        """Get detailed game information"""
        pass
    
    def to_universal_format(self, data: Dict) -> Dict:
        """Convert sport-specific data to universal format"""
        return {
            "sport": self.sport_name,
            "league": self.league_name,
            "event_id": str(data.get("event_id", "")),
            "home_team": data.get("home_team", {}),
            "away_team": data.get("away_team", {}),
            "start_time": data.get("start_time"),
            "status": data.get("status", "SCHEDULED"),
            "venue": data.get("venue"),
            "home_score": data.get("home_score", 0),
            "away_score": data.get("away_score", 0),
            "sport_data": data.get("sport_data", {}),
        }


class SportGateway:
    """Gateway to access all sport adapters"""
    
    def __init__(self):
        self._adapters: Dict[str, BaseSportAdapter] = {}
        self._register_default_adapters()
    
    def _register_default_adapters(self):
        """Register available adapters"""
        # Will be populated as we add sport clients
        pass
    
    def register_adapter(self, sport: str, adapter: BaseSportAdapter):
        """Register a new sport adapter"""
        self._adapters[sport] = adapter
    
    def get_adapter(self, sport: str) -> Optional[BaseSportAdapter]:
        """Get adapter for a sport"""
        return self._adapters.get(sport.lower())
    
    def get_fixtures(self, sport: str, date: Optional[str] = None, days_ahead: int = 1) -> List[Dict]:
        """Get fixtures for a sport"""
        adapter = self.get_adapter(sport)
        if adapter:
            return adapter.get_fixtures(date, days_ahead)
        return []
    
    def get_live_games(self, sport: str) -> List[Dict]:
        """Get live games for a sport"""
        adapter = self.get_adapter(sport)
        if adapter:
            return adapter.get_live_games()
        return []
    
    def get_all_sports(self) -> List[str]:
        """Get list of available sports"""
        return list(self._adapters.keys())


# Sport constants
class Sport:
    MLB = "mlb"
    NBA = "nba"
    NFL = "nfl"
    NHL = "nhl"
    TENNIS = "tennis"
    FOOTBALL = "football"
    
    ALL = [MLB, NBA, NFL, NHL, TENNIS, FOOTBALL]


# Market constants for each sport
class Market:
    # MLB
    MLB_MONEYLINE = "mlb_moneyline"
    MLB_TOTAL = "mlb_total"
    MLB_RUNLINE = "mlb_runline"
    MLB_PROPS = "mlb_props"
    
    # NBA
    NBA_MONEYLINE = "nba_moneyline"
    NBA_SPREAD = "nba_spread"
    NBA_TOTAL = "nba_total"
    NBA_PROPS = "nba_props"
    
    #通用
    MONEYLINE = "moneyline"
    SPREAD = "spread"
    TOTAL = "total"
    PROPS = "props"
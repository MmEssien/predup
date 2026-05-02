"""
MLB API Client using API-Sports
Base URL: v1.baseball.api-sports.io
API Key: From API_SPORTS_KEY env variable
"""

import os
import logging
import time
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from pathlib import Path
import json
import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def get_current_mlb_season() -> int:
    """Get MLB season - free plan supports 2022-2024"""
    # Free plan only supports 2022-2024 seasons
    return 2024  # Use 2024 season for free plan


class MLBApiSportsClient:
    """Client for MLB data via api-sports.io API"""
    
    BASE_URL = "https://v1.baseball.api-sports.io"
    
    CACHE_TTL = {
        "fixtures": 3600,        # 1 hour
        "standings": 43200,      # 12 hours
        "teams": 86400,         # 24 hours
        "player_stats": 21600,   # 6 hours
        "odds": 300,            # 5 minutes
        "games": 3600,          # 1 hour
    }
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("API_SPORTS_KEY") or "fee203af0cddf8fbb26d962335be4362"
        self.timeout = 30
        self.max_retries = 3
        self.retry_delay = 2
        self._client: Optional[httpx.Client] = None
        
        self._headers = {
            "x-apisports-key": self.api_key,
            "Content-Type": "application/json"
        }
    
    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                headers=self._headers,
                timeout=self.timeout
            )
        return self._client
    
    def close(self):
        if self._client:
            self._client.close()
            self._client = None
    
    def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        use_cache: bool = True
    ) -> Dict:
        """Make API request with retry logic"""
        
        url = f"{self.BASE_URL}{endpoint}"
        
        for attempt in range(self.max_retries):
            try:
                response = self.client.get(url, params=params)
                
                if response.status_code == 429:
                    logger.warning(f"Rate limited, retrying in {self.retry_delay}s...")
                    time.sleep(self.retry_delay)
                    continue
                
                response.raise_for_status()
                return response.json()
                
            except httpx.TimeoutException:
                logger.warning(f"Timeout on attempt {attempt + 1}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
            except Exception as e:
                logger.error(f"API error: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                else:
                    return {"results": 0, "response": []}
        
        return {"results": 0, "response": []}
    
    def get_games(self, date: Optional[str] = None, season: int = None, league: int = 1) -> Dict:
        """Get MLB games"""
        if season is None:
            season = get_current_mlb_season()
        
        params = {"season": season, "league": league}
        if date:
            params["date"] = date
        
        return self._make_request("/games", params=params)
    
    def get_fixtures(self, date: Optional[str] = None, season: int = None) -> Dict:
        """Get MLB fixtures (alias for games)"""
        return self.get_games(date, season)
    
    def get_teams(self, league: int = 1, season: int = None) -> Dict:
        """Get all MLB teams"""
        if season is None:
            season = get_current_mlb_season()
        
        params = {"league": league, "season": season}
        return self._make_request("/teams", params=params)
    
    def get_team(self, team_id: int) -> Dict:
        """Get single team details"""
        return self._make_request(f"/teams?id={team_id}")
    
    def get_standings(self, league: int = 1, season: int = None) -> Dict:
        """Get MLB standings"""
        if season is None:
            season = get_current_mlb_season()
        
        params = {"season": season, "league": league}
        return self._make_request("/standings", params=params)
    
    def get_odds(self, date: Optional[str] = None, league: int = 1, season: int = None) -> Dict:
        """Get MLB betting odds"""
        if season is None:
            season = get_current_mlb_season()
        
        params = {"league": league, "season": season}
        if date:
            params["date"] = date
        
        return self._make_request("/odds", params=params)
    
    def get_injuries(self, league: int = 1, season: int = None) -> Dict:
        """Get MLB injuries"""
        if season is None:
            season = get_current_mlb_season()
        
        params = {"league": league, "season": season}
        return self._make_request("/injuries", params=params)
    
    def get_player(self, player_id: int) -> Dict:
        """Get player details"""
        return self._make_request(f"/players?id={player_id}")
    
    def get_player_stats(self, player_id: int, season: int = None) -> Dict:
        """Get player statistics"""
        if season is None:
            season = get_current_mlb_season()
        
        params = {"player": player_id, "season": season}
        return self._make_request("/players/statistics", params=params)
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class MLBApiSportsMapper:
    """Map MLB API-Sports data to unified format"""
    
    @staticmethod
    def map_game(game: Dict) -> Dict:
        """Map MLB game to unified fixture format"""
        teams = game.get("teams", {})
        home = teams.get("home", {})
        away = teams.get("visitors", {})
        
        return {
            "sport": "mlb",
            "event_id": str(game.get("id", "")),
            "league": "MLB",
            "home_team": {
                "id": home.get("id"),
                "name": home.get("name"),
                "abbreviation": home.get("code"),
            },
            "away_team": {
                "id": away.get("id"),
                "name": away.get("name"),
                "abbreviation": away.get("code"),
            },
            "start_time": game.get("date"),
            "status": game.get("status", {}).get("long", "UNKNOWN"),
            "status_short": game.get("status", {}).get("short", ""),
            "venue": game.get("venue", {}).get("name") if game.get("venue") else None,
            "game_id": game.get("id"),
        }
    
    @staticmethod
    def map_team(team: Dict) -> Dict:
        """Map MLB team data"""
        return {
            "id": team.get("id"),
            "name": team.get("name"),
            "nickname": team.get("nickname"),
            "code": team.get("code"),
            "logo": team.get("logo"),
            "city": team.get("city"),
        }
    
    @staticmethod
    def map_standings(standings: List[Dict]) -> List[Dict]:
        """Map standings data"""
        result = []
        for standing in standings:
            result.append({
                "team_id": standing.get("team", {}).get("id"),
                "team_name": standing.get("team", {}).get("name"),
                "conference": standing.get("conference", {}).get("name"),
                "division": standing.get("division", {}).get("name"),
                "rank": standing.get("position"),
                "win": standing.get("win", {}).get("total"),
                "loss": standing.get("loss", {}).get("total"),
                "win_pct": standing.get("win", {}).get("percentage"),
                "games_behind": standing.get("gamesBehind"),
            })
        return result


# Test the client
if __name__ == "__main__":
    print("=== Testing MLB API-Sports Client ===\n")
    
    client = MLBApiSportsClient()
    
    # Test games
    print("Fetching MLB games...")
    games = client.get_games()
    print(f"  Games found: {games.get('results', 0)}")
    
    if games.get("response"):
        for g in games["response"][:3]:
            mapped = MLBApiSportsMapper.map_game(g)
            print(f"    {mapped['away_team']['name']} @ {mapped['home_team']['name']}")
    
    # Test teams
    print("\nFetching MLB teams...")
    teams = client.get_teams()
    print(f"  Teams found: {teams.get('results', 0)}")
    
    client.close()
    print("\n[COMPLETE]")

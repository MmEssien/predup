"""
NBA API Client using API-Sports
Base URL: v2.nba.api-sports.io
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


def get_current_nba_season() -> int:
    """Get NBA season - free plan supports 2022-2024"""
    # Free plan only supports 2022-2024 seasons
    return 2024  # Use 2024 season for free plan


class NBADataCache:
    """Simple file-based cache for NBA API responses"""
    
    def __init__(self, cache_dir: str = "cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
    
    def _get_cache_path(self, key: str) -> Path:
        """Get cache file path for a key"""
        safe_key = key.replace("/", "_").replace(":", "_")
        return self.cache_dir / f"nba_{safe_key}.json"
    
    def get(self, key: str, max_age_seconds: int) -> Optional[Dict]:
        """Get cached data if not expired"""
        cache_file = self._get_cache_path(key)
        
        if not cache_file.exists():
            return None
        
        try:
            mtime = cache_file.stat().st_mtime
            age = time.time() - mtime
            
            if age > max_age_seconds:
                return None
            
            with open(cache_file) as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Cache read error for {key}: {e}")
            return None
    
    def set(self, key: str, data: Dict) -> None:
        """Save data to cache"""
        cache_file = self._get_cache_path(key)
        
        try:
            with open(cache_file, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning(f"Cache write error for {key}: {e}")


class NBAApiSportsClient:
    """Client for NBA data via api-sports.io API"""
    
    BASE_URL = "https://v2.nba.api-sports.io"
    
    CACHE_TTL = {
        "fixtures": 3600,        # 1 hour
        "standings": 43200,      # 12 hours
        "team_stats": 86400,     # 24 hours
        "player_stats": 21600,   # 6 hours
        "odds": 300,             # 5 minutes
        "games": 3600,           # 1 hour
    }
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("API_SPORTS_KEY") or "fee203af0cddf8fbb26d962335be4362"
        self.timeout = 30
        self.max_retries = 3
        self.retry_delay = 2
        self._client: Optional[httpx.Client] = None
        self._cache = NBADataCache()
        
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
        cache_key: Optional[str] = None,
        cache_ttl: Optional[int] = None,
        use_cache: bool = True
    ) -> Dict:
        """Make API request with retry and caching"""
        
        # Check cache first
        if use_cache and cache_key:
            cached = self._cache.get(cache_key, cache_ttl or 3600)
            if cached:
                logger.debug(f"Cache hit for {endpoint}")
                return cached
        
        url = f"{self.BASE_URL}{endpoint}"
        
        for attempt in range(self.max_retries):
            try:
                response = self.client.get(url, params=params)
                
                if response.status_code == 429:
                    logger.warning(f"Rate limited, retrying in {self.retry_delay}s...")
                    time.sleep(self.retry_delay)
                    continue
                
                response.raise_for_status()
                data = response.json()
                
                # Cache the response
                if use_cache and cache_key and data.get("results", 0) > 0:
                    self._cache.set(cache_key, data)
                
                return data
                
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
    
    def get_games(self, date: Optional[str] = None, season: int = None) -> Dict:
        """Get NBA games"""
        if season is None:
            season = get_current_nba_season()
        
        params = {"season": season}
        if date:
            params["date"] = date
        
        # Bypass cache - make direct request
        url = f"{self.BASE_URL}/games"
        response = self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()
    
    def get_fixtures(self, date: Optional[str] = None, league: int = 1) -> Dict:
        """Get NBA fixtures (alias for games)"""
        return self.get_games(date, league)
    
    def get_h2h(self, h2h: str, date: Optional[str] = None) -> Dict:
        """Get head-to-head games between teams"""
        params = {"h2h": h2h}
        if date:
            params["date"] = date
        
        return self._make_request("/games", params=params)
    
    def get_teams(self) -> Dict:
        """Get all NBA teams"""
        return self._make_request(
            "/teams",
            params={},
            cache_key="teams",
            cache_ttl=self.CACHE_TTL["team_stats"]
        )
    
    def get_team(self, team_id: int) -> Dict:
        """Get single team details"""
        return self._make_request(
            f"/teams?id={team_id}",
            cache_key=f"team_{team_id}",
            cache_ttl=self.CACHE_TTL["team_stats"]
        )
    
    def get_team_stats(self, team_id: int, season: Optional[int] = None) -> Dict:
        """Get team statistics for a season"""
        params = {"team": team_id}
        if season:
            params["season"] = season
        else:
            params["season"] = datetime.now().year
        
        return self._make_request(
            "/teams/statistics",
            params=params,
            cache_key=f"team_stats_{team_id}_{season}",
            cache_ttl=self.CACHE_TTL["team_stats"]
        )
    
    def get_players(self, team_id: int, season: Optional[int] = None) -> Dict:
        """Get players for a team"""
        params = {"team": team_id}
        if season:
            params["season"] = season
        else:
            params["season"] = datetime.now().year
        
        return self._make_request(
            "/players",
            params=params,
            cache_key=f"players_{team_id}_{season}",
            cache_ttl=self.CACHE_TTL["player_stats"]
        )
    
    def get_player_stats(self, player_id: int, season: Optional[int] = None) -> Dict:
        """Get player statistics"""
        params = {"player": player_id}
        if season:
            params["season"] = season
        else:
            params["season"] = datetime.now().year
        
        return self._make_request(
            "/players/statistics",
            params=params,
            cache_key=f"player_stats_{player_id}_{season}",
            cache_ttl=self.CACHE_TTL["player_stats"]
        )
    
    def get_standings(self, season: int = None) -> Dict:
        """Get NBA standings"""
        if season is None:
            season = get_current_nba_season()
        params = {"season": season}
        
        return self._make_request(
            "/standings",
            params=params,
            cache_key=f"standings_{season}",
            cache_ttl=self.CACHE_TTL["standings"]
        )
    
    def get_injuries(self, season: int = None) -> Dict:
        """Get NBA injuries"""
        if season is None:
            season = get_current_nba_season()
        params = {"season": season}
        
        return self._make_request(
            "/injuries",
            params=params,
            cache_key=f"injuries_{season}",
            cache_ttl=self.CACHE_TTL["player_stats"]
        )
    
    def get_odds(
        self,
        date: Optional[str] = None,
        bookmaker: int = 1,
        season: int = None
    ) -> Dict:
        """Get NBA betting odds"""
        if season is None:
            season = get_current_nba_season()
        params = {"bookmaker": bookmaker, "season": season}
        if date:
            params["date"] = date
        else:
            params["date"] = datetime.now().strftime("%Y-%m-%d")
        
        return self._make_request(
            "/odds",
            params=params,
            cache_key=f"odds_{date or 'today'}",
            cache_ttl=self.CACHE_TTL["odds"]
        )
    
    def get_game_details(self, game_id: int) -> Dict:
        """Get detailed game information"""
        return self._make_request(
            f"/games/id/{game_id}",
            cache_key=f"game_{game_id}",
            cache_ttl=self.CACHE_TTL["fixtures"]
        )
    
    def get_games_by_date_range(
        self,
        start_date: str,
        end_date: str,
        league: int = 1
    ) -> List[Dict]:
        """Get games in date range"""
        results = []
        
        current = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        
        while current <= end:
            date_str = current.strftime("%Y-%m-%d")
            games = self.get_games(date_str, league)
            
            for g in games.get("response", []):
                results.append(g)
            
            current += timedelta(days=1)
        
        return results
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class NBADataMapper:
    """Map NBA API data to unified format"""
    
    @staticmethod
    def map_game(game: Dict) -> Dict:
        """Map NBA game to unified fixture format"""
        teams = game.get("teams", {})
        visitors = teams.get("visitors", {})  # API uses visitors for away
        home = teams.get("home", {})
        
        return {
            "sport": "nba",
            "event_id": str(game.get("id", "")),
            "league": "NBA",
            "home_team": {
                "id": home.get("id"),
                "name": home.get("name"),
                "abbreviation": home.get("code"),
                "score": game.get("scores", {}).get("home", {}).get("points"),
            },
            "away_team": {
                "id": visitors.get("id"),
                "name": visitors.get("name"),
                "abbreviation": visitors.get("code"),
                "score": game.get("scores", {}).get("visitors", {}).get("points"),
            },
            "start_time": game.get("date", {}).get("start"),
            "status": game.get("status", {}).get("long", "UNKNOWN"),
            "status_short": game.get("status", {}).get("short", ""),
            "venue": game.get("arena", {}).get("name") if game.get("arena") else None,
            "game_id": game.get("id"),
            "period": game.get("periods", {}).get("current"),
            "quarter": game.get("periods", {}).get("quarter"),
        }
    
    @staticmethod
    def map_team(team: Dict) -> Dict:
        """Map NBA team data"""
        return {
            "id": team.get("id"),
            "name": team.get("name"),
            "nickname": team.get("nickname"),
            "code": team.get("code"),
            "logo": team.get("logo"),
            "city": team.get("city"),
            "arena": team.get("arena"),
            "conference": team.get("league", {}).get("standard", {}).get("conference", ""),
            "division": team.get("league", {}).get("standard", {}).get("division", ""),
        }
    
    @staticmethod
    def map_team_stats(stats: Dict) -> Dict:
        """Map team statistics"""
        response = stats.get("response", [{}])[0]
        return {
            "team_id": response.get("team", {}).get("id"),
            "games_played": response.get("games", {}).get("played"),
            "points_for": response.get("points", {}).get("for"),
            "points_against": response.get("points", {}).get("against"),
            "win": response.get("win", {}).get("total"),
            "loss": response.get("loss", {}).get("total"),
            "win_home": response.get("win", {}).get("home"),
            "win_away": response.get("win", {}).get("away"),
            "loss_home": response.get("loss", {}).get("home"),
            "loss_away": response.get("loss", {}).get("away"),
            "streak": response.get("streak"),
            "min": response.get("games", {}).get("minutes"),
        }
    
    @staticmethod
    def map_player_stats(stats: Dict) -> Dict:
        """Map player statistics"""
        response = stats.get("response", [{}])[0]
        player = response.get("player", {})
        teams = response.get("teams", [{}])[0] if response.get("teams") else {}
        
        return {
            "player_id": player.get("id"),
            "player_name": player.get("name"),
            "team_id": teams.get("team", {}).get("id"),
            "team_name": teams.get("team", {}).get("name"),
            "games_played": response.get("games", {}).get("played"),
            "points_avg": response.get("points", {}).get("avg"),
            "minutes_avg": response.get("minutes", {}).get("avg"),
            "fgm_avg": response.get("fgm", {}).get("avg"),
            "fga_avg": response.get("fga", {}).get("avg"),
            "fgp_avg": response.get("fgp", {}).get("avg"),
            "reb_avg": response.get("reb", {}).get("avg"),
            "ast_avg": response.get("assists", {}).get("avg"),
            "stl_avg": response.get("steals", {}).get("avg"),
            "blk_avg": response.get("blocks", {}).get("avg"),
            "turnovers_avg": response.get("turnovers", {}).get("avg"),
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
                "win_home": standing.get("win", {}).get("home"),
                "win_away": standing.get("win", {}).get("away"),
                "win_last_10": standing.get("win", {}).get("lastTen"),
                "streak": standing.get("streak"),
                "games_behind": standing.get("gamesBehind"),
                "points_for": standing.get("pointsFor"),
                "points_against": standing.get("pointsAgainst"),
            })
        return result
    
    @staticmethod
    def map_injury(injury: Dict) -> Dict:
        """Map injury data"""
        return {
            "player_id": injury.get("player", {}).get("id"),
            "player_name": injury.get("player", {}).get("name"),
            "team_id": injury.get("team", {}).get("id"),
            "team_name": injury.get("team", {}).get("name"),
            "description": injury.get("description"),
            "date": injury.get("date"),
            "player_status": injury.get("player", {}).get("injury", {}).get("status"),
        }


# Test NBA client
if __name__ == "__main__":
    print("=== Testing NBA API-Sports Client ===\n")
    
    client = NBAApiSportsClient()
    
    # Test teams
    print("Fetching NBA teams...")
    teams = client.get_teams()
    print(f"  Teams found: {teams.get('results', 0)}")
    
    if teams.get("response"):
        for t in teams["response"][:3]:
            print(f"    - {t.get('name')} ({t.get('code')})")
    
    # Test games today
    print("\nFetching today's games...")
    games = client.get_games()
    print(f"  Games found: {games.get('results', 0)}")
    
    if games.get("response"):
        for g in games["response"][:3]:
            home = g.get("teams", {}).get("home", {}).get("name", "?")
            away = g.get("teams", {}).get("away", {}).get("name", "?")
            status = g.get("status", {}).get("short", "TBD")
            print(f"    {away} @ {home} [{status}]")
    
    # Test standings
    print("\nFetching standings...")
    standings = client.get_standings()
    print(f"  Standings entries: {standings.get('results', 0)}")
    
    # Test odds
    print("\nFetching odds...")
    odds = client.get_odds()
    print(f"  Odds found: {odds.get('results', 0)}")
    
    client.close()
    print("\n[COMPLETE]")
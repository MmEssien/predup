"""
MLB API Client using MLB StatsAPI
Base URL: https://statsapi.mlb.com/api/v1/
"""

import os
import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
import httpx

logger = logging.getLogger(__name__)


class MLBStatsClient:
    """Client for MLB StatsAPI (statsapi.mlb.com)"""
    
    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://statsapi.mlb.com/api/v1"):
        self.api_key = api_key or os.getenv("MLB_STATS_API_KEY")
        self.base_url = base_url
        self.timeout = 30
        self._client: Optional[httpx.Client] = None
    
    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client
    
    def close(self):
        if self._client:
            self._client.close()
            self._client = None
    
    def get_schedule(
        self, 
        date: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        sport_id: int = 1
    ) -> Dict:
        """Get game schedule"""
        params = {"sportId": sport_id}
        
        if date:
            params["date"] = date
        if start_date:
            params["startDate"] = start_date
        if end_date:
            params["endDate"] = end_date
        
        try:
            response = self.client.get(f"{self.base_url}/schedule", params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get schedule: {e}")
            return {}
    
    def get_teams(self, sport_id: int = 1) -> List[Dict]:
        """Get all teams"""
        try:
            response = self.client.get(f"{self.base_url}/teams", params={"sportId": sport_id})
            response.raise_for_status()
            data = response.json()
            return data.get("teams", [])
        except Exception as e:
            logger.error(f"Failed to get teams: {e}")
            return []
    
    def get_team(self, team_id: int) -> Optional[Dict]:
        """Get single team details"""
        try:
            response = self.client.get(f"{self.base_url}/teams/{team_id}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get team {team_id}: {e}")
            return None
    
    def get_game_boxscore(self, game_pk: int) -> Dict:
        """Get boxscore for a game"""
        try:
            response = self.client.get(f"{self.base_url}/game/{game_pk}/boxscore")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get boxscore for {game_pk}: {e}")
            return {}
    
    def get_game_feed(self, game_pk: int) -> Dict:
        """Get live feed for a game"""
        try:
            response = self.client.get(f"{self.base_url}/game/{game_pk}/feed/live")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get feed for {game_pk}: {e}")
            return {}
    
    def get_player_stats(self, person_id: int, stats_type: str = "season") -> Dict:
        """Get player stats"""
        try:
            response = self.client.get(
                f"{self.base_url}/people/{person_id}/stats",
                params={"stats": stats_type}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get stats for player {person_id}: {e}")
            return {}
    
    def get_leaders(self, leader_categories: List[str], limit: int = 10) -> Dict:
        """Get league leaders"""
        try:
            response = self.client.get(
                f"{self.base_url}/leaders",
                params={
                    "leaderCategories": ",".join(leader_categories),
                    "limit": limit
                }
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get leaders: {e}")
            return {}
    
    def get_standings(self, date: Optional[str] = None) -> Dict:
        """Get current standings"""
        params = {}
        if date:
            params["date"] = date
        
        try:
            response = self.client.get(f"{self.base_url}/standings", params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get standings: {e}")
            return {}
    
    def get_probable_pitchers(self, date: str) -> Dict:
        """Get probable pitchers for a date"""
        try:
            response = self.client.get(
                f"{self.base_url}/schedule",
                params={"sportId": 1, "date": date, "hydrate": "probablePitcher"}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get probable pitchers: {e}")
            return {}
    
    # Convenience methods for prediction system
    
    def get_todays_games(self) -> List[Dict]:
        """Get today's games"""
        today = datetime.now().strftime("%Y-%m-%d")
        return self.get_schedule(date=today)
    
    def get_upcoming_games(self, days: int = 3) -> List[Dict]:
        """Get upcoming games for next N days"""
        start = datetime.now()
        start_date = start.strftime("%Y-%m-%d")
        end = start + timedelta(days=days)
        end_date = end.strftime("%Y-%m-%d")
        
        data = self.get_schedule(start_date=start_date, end_date=end_date)
        
        games = []
        dates = data.get("dates", [])
        for date_obj in dates:
            for game in date_obj.get("games", []):
                games.append(game)
        
        return games
    
    def get_team_stats(self, team_id: int) -> Optional[Dict]:
        """Get team stats for the season"""
        # This would need to fetch from team stats endpoint
        # Simplified for now
        return self.get_team(team_id)
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class MLBDataMapper:
    """Map MLB API data to unified format"""
    
    @staticmethod
    def map_game(game: Dict) -> Dict:
        """Map MLB game to unified fixture format"""
        game_pk = game.get("gamePk")
        teams = game.get("teams", {})
        
        home = teams.get("home", {})
        away = teams.get("away", {})
        
        return {
            "sport": "mlb",
            "event_id": str(game_pk),
            "league": "MLB",
            "home_team": {
                "id": home.get("team", {}).get("id"),
                "name": home.get("team", {}).get("name"),
                "abbreviation": home.get("team", {}).get("abbreviation"),
                "score": home.get("score"),
                "record": f"{home.get('leagueRecord', {}).get('wins', 0)}-{home.get('leagueRecord', {}).get('losses', 0)}"
            },
            "away_team": {
                "id": away.get("team", {}).get("id"),
                "name": away.get("team", {}).get("name"),
                "abbreviation": away.get("team", {}).get("abbreviation"),
                "score": away.get("score"),
                "record": f"{away.get('leagueRecord', {}).get('wins', 0)}-{away.get('leagueRecord', {}).get('losses', 0)}"
            },
            "start_time": game.get("gameDate"),
            "status": game.get("status", {}).get("abstractGameState", "UNKNOWN"),
            "venue": game.get("venue", {}).get("name"),
            "game_pk": game_pk
        }
    
    @staticmethod
    def map_boxscore(boxscore: Dict) -> Dict:
        """Map boxscore to stats format"""
        teams = boxscore.get("teams", {})
        
        result = {
            "game_pk": boxscore.get("gamePk"),
            "status": boxscore.get("status", {}).get("abstractGameState")
        }
        
        for side in ["home", "away"]:
            team_data = teams.get(side, {})
            team_stats = team_data.get("teamStats", {}).get("batting", {})
            pitches = team_data.get("teamStats", {}).get("pitching", {})
            
            result[f"{side}_team_id"] = team_data.get("team", {}).get("id")
            result[f"{side}_runs"] = team_stats.get("runs")
            result[f"{side}_hits"] = team_stats.get("hits")
            result[f"{side}_errors"] = team_stats.get("errors")
            result[f"{side}_pitch_count"] = pitches.get("pitchesThrown")
            
            # Find winning pitcher
            for pitcher in team_data.get("players", {}).get("IDPitching", []):
                if pitcher.get("stats", {}).get("pitching", {}).get("win"):
                    result[f"{side}_winning_pitcher"] = pitcher.get("person", {}).get("fullName")
        
        return result
    
    @staticmethod
    def map_team(team: Dict) -> Dict:
        """Map team data"""
        return {
            "id": team.get("id"),
            "name": team.get("name"),
            "abbreviation": team.get("abbreviation"),
            "team_code": team.get("teamCode"),
            "league": team.get("league", {}).get("name"),
            "division": team.get("division", {}).get("name"),
            "venue": team.get("venue", {}).get("name"),
            "short_name": team.get("shortName"),
            "file_code": team.get("fileCode")
        }


if __name__ == "__main__":
    # Test the client
    client = MLBStatsClient()
    
    print("=== Testing MLB API ===")
    
    # Get teams
    teams = client.get_teams()
    print(f"Total teams: {len(teams)}")
    if teams:
        for t in teams[:3]:
            team = t.get("team", {})
            print(f"  - {team.get('name')} ({team.get('abbreviation')})")
    
    # Get today's games
    games = client.get_todays_games()
    dates = games.get("dates", [])
    print(f"Today's games: {len(dates)}")
    if dates:
        for d in dates[:1]:
            print(f"  Date: {d.get('date')}")
            for g in d.get("games", [])[:3]:
                home = g.get("teams", {}).get("home", {}).get("team", {}).get("name", "?")
                away = g.get("teams", {}).get("away", {}).get("team", {}).get("name", "?")
                print(f"    {away} @ {home}")
    
    client.close()
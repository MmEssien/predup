"""
NBA Stats Fallback Client - Uses stats.nba.com official NBA stats
Fallback data source when api-sports is unavailable
"""

import logging
import httpx
from typing import Optional, Dict, List
from datetime import datetime

logger = logging.getLogger(__name__)


class NBAStatsFallback:
    """Fallback client using stats.nba.com official NBA stats API"""
    
    BASE_URL = "https://stats.nba.com/stats"
    
    def __init__(self):
        self._client: Optional[httpx.Client] = None
        self._timeout = 15
    
    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Host": "stats.nba.com",
                    "Connection": "keep-alive",
                },
                timeout=self._timeout
            )
        return self._client
    
    def close(self):
        if self._client:
            self._client.close()
            self._client = None
    
    def get_team_info(self, team_id: int, season: str = "2024-25") -> Optional[Dict]:
        """Get team info from stats.nba.com"""
        try:
            params = {
                "LeagueID": "00",
                "TeamID": team_id,
                "Season": season,
                "SeasonType": "Regular Season"
            }
            response = self.client.get(f"{self.BASE_URL}/teamdetails", params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get team info from stats.nba.com: {e}")
            return None
    
    def get_team_stats(self, team_id: int, season: str = "2024-25") -> Optional[Dict]:
        """Get team general stats"""
        try:
            params = {
                "LeagueID": "00",
                "TeamID": team_id,
                "Season": season,
                "SeasonType": "Regular Season",
                "PerMode": "Totals"
            }
            response = self.client.get(f"{self.BASE_URL}/teaminfocommon", params=params)
            response.raise_for_status()
            data = response.json()
            
            result_set = data.get("resultSets", [{}])[0]
            headers = result_set.get("headers", [])
            row = result_set.get("rowSet", [[]])[0]
            
            if headers and row:
                return dict(zip(headers, row))
        except Exception as e:
            logger.error(f"Failed to get team stats: {e}")
        
        return None
    
    def get_player_stats(self, player_id: int, season: str = "2024-25") -> Optional[Dict]:
        """Get player career stats"""
        try:
            params = {
                "LeagueID": "00",
                "PlayerID": player_id,
                "Season": season,
                "SeasonType": "Regular Season"
            }
            response = self.client.get(f"{self.BASE_URL}/playercareerstats", params=params)
            response.raise_for_status()
            data = response.json()
            
            result_set = data.get("resultSets", [{}])[0]
            headers = result_set.get("headers", [])
            row = result_set.get("rowSet", [[]])[0] if result_set.get("rowSet") else []
            
            if headers and row:
                return dict(zip(headers, row))
        except Exception as e:
            logger.error(f"Failed to get player stats: {e}")
        
        return None
    
    def get_league_leaders(self, stat: str = "PTS", season: str = "2024-25") -> List[Dict]:
        """Get league leaders for a stat"""
        try:
            params = {
                "LeagueID": "00",
                "Season": season,
                "SeasonType": "Regular Season",
                "StatCategory": stat,
                "PerMode": "PerGame"
            }
            response = self.client.get(f"{self.BASE_URL}/leagueleaders", params=params)
            response.raise_for_status()
            data = response.json()
            
            result_set = data.get("resultSets", [{}])[0]
            headers = result_set.get("headers", [])
            rows = result_set.get("rowSet", [])
            
            return [dict(zip(headers, row)) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get league leaders: {e}")
        
        return []
    
    def get_scoreboard(self, game_date: Optional[str] = None) -> List[Dict]:
        """Get scoreboard for a date"""
        try:
            if game_date is None:
                game_date = datetime.now().strftime("%m/%d/%Y")
            
            params = {
                "LeagueID": "00",
                "GameDate": game_date,
                "GameScope": "Detailed",
                "LeagueID": "00",
                "Season": "2024-25",
                "SeasonType": "Regular Season",
                "hg": "0",
                "vt": "0"
            }
            response = self.client.get(f"{self.BASE_URL}/scoreboard", params=params)
            response.raise_for_status()
            data = response.json()
            
            return data.get("gs", [])
        except Exception as e:
            logger.error(f"Failed to get scoreboard: {e}")
        
        return []
    
    def get_injury_report(self) -> List[Dict]:
        """Get injury report"""
        try:
            params = {
                "LeagueID": "00",
                "Season": "2024-25",
                "SeasonType": "Regular Season"
            }
            response = self.client.get(f"{self.BASE_URL}/injurynotes", params=params)
            response.raise_for_status()
            data = response.json()
            
            return data.get("InjuryNotes", [])
        except Exception as e:
            logger.error(f"Failed to get injury report: {e}")
        
        return []
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Static mapping of team IDs
TEAM_ID_MAP = {
    "Atlanta Hawks": 1610612737,
    "Boston Celtics": 1610612738,
    "Brooklyn Nets": 1610612751,
    "Charlotte Hornets": 1610612766,
    "Chicago Bulls": 1610612741,
    "Cleveland Cavaliers": 1610612739,
    "Dallas Mavericks": 1610612742,
    "Denver Nuggets": 1610612743,
    "Detroit Pistons": 1610612765,
    "Golden State Warriors": 1610612744,
    "Houston Rockets": 1610612745,
    "Indiana Pacers": 1610612754,
    "LA Clippers": 1610612746,
    "Los Angeles Clippers": 1610612746,
    "Los Angeles Lakers": 1610612747,
    "LA Lakers": 1610612747,
    "Memphis Grizzlies": 1610612763,
    "Miami Heat": 1610612748,
    "Milwaukee Bucks": 1610612749,
    "Minnesota Timberwolves": 1610612750,
    "New Orleans Pelicans": 1610612755,
    "New York Knicks": 1610612752,
    "Oklahoma City Thunder": 1610612760,
    "Orlando Magic": 1610612753,
    "Philadelphia 76ers": 1610612755,
    "Phoenix Suns": 1610612756,
    "Portland Trail Blazers": 1610612757,
    "Sacramento Kings": 1610612758,
    "San Antonio Spurs": 1610612759,
    "Toronto Raptors": 1610612761,
    "Utah Jazz": 1610612762,
    "Washington Wizards": 1610612764,
}


def get_team_id(team_name: str) -> Optional[int]:
    """Get stats.nba.com team ID from team name"""
    return TEAM_ID_MAP.get(team_name)


def test_fallback():
    """Test the fallback client"""
    with NBAStatsFallback() as client:
        print("\n=== Testing NBA Stats Fallback ===")
        
        print("\n[1] League leaders (PTS)...")
        leaders = client.get_league_leaders("PTS")
        print(f"  Found {len(leaders)} leaders")
        if leaders:
            print(f"  Top: {leaders[0]}")
        
        print("\n[2] Scoreboard...")
        scoreboard = client.get_scoreboard()
        print(f"  Found {len(scoreboard)} games")
        
        print("\n[3] Injury report...")
        injuries = client.get_injury_report()
        print(f"  Found {len(injuries)} injuries")
    
    print("\n=== Test Complete ===")


if __name__ == "__main__":
    test_fallback()
"""
NBA Sport Adapter - Implements BaseSportAdapter interface
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any

from src.data.nba_client import NBAApiSportsClient, NBADataMapper, get_current_nba_season
from src.data.sport_adapter import BaseSportAdapter


class NBAAdapter(BaseSportAdapter):
    """NBA adapter using API-Sports"""
    
    sport_name = "nba"
    league_name = "NBA"
    
    def __init__(self, api_key: Optional[str] = None):
        self.client = NBAApiSportsClient(api_key)
        self.mapper = NBADataMapper()
        self._teams_cache = None
        self._standings_cache = None
        self._current_season = get_current_nba_season()
    
    def get_fixtures(self, date: Optional[str] = None, days_ahead: int = 1) -> List[Dict]:
        """Get upcoming NBA games"""
        data = self.client.get_games(season=self._current_season)
        all_games = [self.mapper.map_game(g) for g in data.get("response", [])]
        
        if date is None:
            from datetime import datetime, timedelta
            end_date = datetime.now() + timedelta(days=days_ahead)
            start_date = datetime.now()
        else:
            from datetime import datetime, timedelta
            start_date = datetime.strptime(date, "%Y-%m-%d")
            end_date = start_date + timedelta(days=days_ahead)
        
        # Filter by date range
        results = []
        for game in all_games:
            try:
                game_date = datetime.fromisoformat(game["start_time"].replace("Z", "+00:00"))
                if start_date <= game_date <= end_date:
                    results.append(game)
            except:
                pass
        
        return results
    
    def get_live_games(self) -> List[Dict]:
        """Get live NBA games"""
        data = self.client.get_games(season=self._current_season)
        results = []
        
        for game in data.get("response", []):
            status_short = game.get("status", {}).get("short", "")
            if status_short in ["1", "2", "3", "4", "HT", "OT"]:
                results.append(self.mapper.map_game(game))
        
        return results
    
    def get_team_stats(self, team_id: int) -> Dict:
        """Get team statistics"""
        data = self.client.get_team_stats(team_id)
        if data.get("response"):
            return self.mapper.map_team_stats(data)
        return {}
    
    def get_odds(self, event_id: str, market: str = "moneyline") -> Dict:
        """Get betting odds for a game"""
        data = self.client.get_odds()
        
        for odd in data.get("response", []):
            if str(odd.get("game", {}).get("id")) == event_id:
                bookmaker = odd.get("bookmaker", {})
                
                # Find moneyline odds
                ml_odds = {}
                for bet in bookmaker.get("bets", []):
                    if bet.get("name") == "Home Team Win":
                        ml_odds["home"] = bet.get("values", [{}])[0].get("odd")
                    elif bet.get("name") == "Away Team Win":
                        ml_odds["away"] = bet.get("values", [{}])[0].get("odd")
                    elif bet.get("name") == "Home/Away":
                        for v in bet.get("values", []):
                            if v.get("option") == "Home":
                                ml_odds["home"] = v.get("odd")
                            elif v.get("option") == "Away":
                                ml_odds["away"] = v.get("odd")
                
                # Find spread
                spread = None
                for bet in bookmaker.get("bets", []):
                    if "Point Spread" in bet.get("name", ""):
                        for v in bet.get("values", []):
                            if v.get("handicap"):
                                spread = {
                                    "home": v.get("handicap"),
                                    "home_odds": v.get("odd")
                                }
                                break
                
                # Find total
                total = None
                for bet in bookmaker.get("bets", []):
                    if "Total" in bet.get("name", ""):
                        for v in bet.get("values", []):
                            if v.get("handicap"):
                                total = {
                                    "points": v.get("handicap"),
                                    "over_odds": v.get("odd")
                                }
                                break
                
                return {
                    "sport": self.sport_name,
                    "event_id": event_id,
                    "market": market,
                    "odds": {
                        "moneyline": ml_odds,
                        "spread": spread,
                        "total": total
                    },
                    "bookmaker": bookmaker.get("name"),
                    "timestamp": odd.get("update")
                }
        
        return {
            "sport": self.sport_name,
            "event_id": event_id,
            "market": market,
            "odds": {},
            "note": "No odds available for this game"
        }
    
    def get_game_details(self, event_id: str) -> Dict:
        """Get detailed game information"""
        try:
            game_id = int(event_id)
            data = self.client.get_game_details(game_id)
            
            if data.get("response"):
                return self.mapper.map_game(data["response"][0])
        except Exception:
            pass
        
        return {}
    
    def get_standings(self) -> List[Dict]:
        """Get current standings"""
        data = self.client.get_standings(season=self._current_season)
        
        if data.get("response"):
            return self.mapper.map_standings(data["response"])
        
        return []
    
    def get_teams(self) -> List[Dict]:
        """Get all NBA teams"""
        if self._teams_cache is None:
            data = self.client.get_teams(league=12)
            self._teams_cache = [
                self.mapper.map_team(t) for t in data.get("response", [])
            ]
        
        return self._teams_cache
    
    def get_injuries(self) -> List[Dict]:
        """Get current injuries"""
        data = self.client.get_injuries(season=self._current_season)
        
        return [
            self.mapper.map_injury(i) for i in data.get("response", [])
        ]
    
    def get_team_by_id(self, team_id: int) -> Optional[Dict]:
        """Get specific team by ID"""
        data = self.client.get_team(team_id)
        
        if data.get("response"):
            return self.mapper.map_team(data["response"][0])
        
        return None
    
    def close(self):
        """Close the client"""
        self.client.close()


class NBAFeatureEngine:
    """Generate features specific to NBA predictions"""
    
    def __init__(self, adapter: NBAAdapter):
        self.adapter = adapter
    
    def generate_offensive_rating(self, team_stats: Dict) -> float:
        """Calculate offensive rating (points per 100 possessions)"""
        points_for = team_stats.get("points_for", 0)
        games = team_stats.get("games_played", 82)
        
        if games > 0:
            return points_for / games
        return 0.0
    
    def generate_defensive_rating(self, team_stats: Dict) -> float:
        """Calculate defensive rating (points allowed per 100 possessions)"""
        points_against = team_stats.get("points_against", 0)
        games = team_stats.get("games_played", 82)
        
        if games > 0:
            return points_against / games
        return 0.0
    
    def generate_net_rating(self, team_stats: Dict) -> float:
        """Calculate net rating (offensive - defensive)"""
        off_rating = self.generate_offensive_rating(team_stats)
        def_rating = self.generate_defensive_rating(team_stats)
        return off_rating - def_rating
    
    def generate_pace(self, team_stats: Dict) -> float:
        """Estimate pace (possessions per game)"""
        points_for = team_stats.get("points_for", 0)
        points_against = team_stats.get("points_against", 0)
        games = team_stats.get("games_played", 82)
        
        if games > 0:
            total_points = points_for + points_against
            return total_points / games / 2  # rough estimate
        return 0.0
    
    def generate_situational_features(
        self,
        home_team_id: int,
        away_team_id: int,
        days_rest_home: int = 0,
        days_rest_away: int = 0,
        is_back_to_back_home: bool = False,
        is_back_to_back_away: bool = False
    ) -> Dict:
        """Generate situational features"""
        return {
            "home_rest_days": days_rest_home,
            "away_rest_days": days_rest_away,
            "home_b2b": 1 if is_back_to_back_home else 0,
            "away_b2b": 1 if is_back_to_back_away else 0,
            "home_rest_advantage": days_rest_home - days_rest_away,
            "travel_disadvantage": 1 if days_rest_away > days_rest_home else 0,
        }
    
    def generate_form_features(
        self,
        standings: List[Dict],
        team_id: int,
        window: int = 10
    ) -> Dict:
        """Generate recent form features"""
        for standing in standings:
            if standing.get("team_id") == team_id:
                last_10 = standing.get("win_last_10", 0)
                streak = standing.get("streak", "")
                
                return {
                    f"win_last_{window}": last_10,
                    f"win_pct_last_{window}": last_10 / min(window, 10) * 100,
                    "streak": streak,
                    "is_hot": last_10 >= 7,
                    "is_cold": last_10 <= 3,
                }
        
        return {
            f"win_last_{window}": 0,
            f"win_pct_last_{window}": 0,
            "streak": "",
            "is_hot": False,
            "is_cold": True,
        }
    
    def generate_home_away_features(
        self,
        home_stats: Dict,
        away_stats: Dict
    ) -> Dict:
        """Generate home/away specific features"""
        return {
            "home_win_pct": home_stats.get("win", 0) / max(1, home_stats.get("win", 0) + home_stats.get("loss", 0)) if home_stats else 0,
            "home_win_pct_home": home_stats.get("win_home", 0) / max(1, home_stats.get("win_home", 0) + home_stats.get("loss_home", 0)) if home_stats else 0,
            "away_win_pct": away_stats.get("win", 0) / max(1, away_stats.get("win", 0) + away_stats.get("loss", 0)) if away_stats else 0,
            "away_win_pct_away": away_stats.get("win_away", 0) / max(1, away_stats.get("win_away", 0) + away_stats.get("loss_away", 0)) if away_stats else 0,
        }


# Test the NBA adapter
if __name__ == "__main__":
    print("=== Testing NBA Adapter ===\n")
    
    adapter = NBAAdapter()
    
    # Get teams
    print("NBA Teams:")
    teams = adapter.get_teams()
    print(f"  Total: {len(teams)} teams")
    for t in teams[:5]:
        print(f"    - {t.get('name')} ({t.get('code')})")
    
    # Get today's games
    print("\nToday's NBA Games:")
    games = adapter.get_fixtures()
    print(f"  Games: {len(games)}")
    for game in games:
        print(f"    {game['away_team']['name']} @ {game['home_team']['name']}")
        print(f"      Status: {game['status']}, Time: {game['start_time']}")
    
    # Get standings
    print("\nStandings:")
    standings = adapter.get_standings()
    print(f"  Entries: {len(standings)}")
    if standings:
        print(f"    Top: {standings[0].get('team_name')} ({standings[0].get('win')}-{standings[0].get('loss')})")
    
    # Get injuries
    print("\nInjuries:")
    injuries = adapter.get_injuries()
    print(f"  Total: {len(injuries)}")
    
    adapter.close()
    print("\n[COMPLETE]")
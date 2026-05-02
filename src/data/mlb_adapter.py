"""
MLB Sport Adapter - Implements BaseSportAdapter interface
Uses API-Sports as PRIMARY (v1.baseball.api-sports.io)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any

from src.data.mlb_api_sports_client import MLBApiSportsClient, MLBApiSportsMapper
from src.data.sport_adapter import BaseSportAdapter


class MLBAdapter(BaseSportAdapter):
    """MLB adapter using API-Sports (PRIMARY)"""
    
    sport_name = "mlb"
    league_name = "MLB"
    
    def __init__(self):
        self.client = MLBApiSportsClient()
        self.mapper = MLBApiSportsMapper()
    
    def get_fixtures(self, date: Optional[str] = None, days_ahead: int = 1) -> List[Dict]:
        """Get MLB games via API-Sports - returns all games for season"""
        data = self.client.get_games()
        return [self.mapper.map_game(g) for g in data.get("response", [])]
    
    def get_todays_games(self) -> List[Dict]:
        """Get today's MLB games - for routes.py compatibility"""
        return self.get_fixtures(days_ahead=1)
    
    def get_live_games(self) -> List[Dict]:
        """Get live MLB games"""
        data = self.client.get_games()
        results = []
        
        for game in data.get("response", []):
            status_short = game.get("status", {}).get("short", "")
            # MLB live statuses: 1=Not Started, 2=In Progress, 3=Final
            if status_short in ["2", "3", "HT", "OT"]:
                results.append(self.mapper.map_game(game))
        
        return results
    
    def get_team_stats(self, team_id: int) -> Dict:
        """Get team statistics"""
        data = self.client.get_team_stats(team_id)
        if data.get("response"):
            return self.mapper.map_team_stats(data)
        return {}
    
    def get_odds(self, event_id: str, market: str = "moneyline") -> Dict:
        """Get betting odds for a game via API-Sports"""
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
                
                return {
                    "sport": self.sport_name,
                    "event_id": event_id,
                    "market": market,
                    "odds": ml_odds,
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
        data = self.client.get_standings()
        if data.get("response"):
            return self.mapper.map_standings(data["response"])
        return []
    
    def get_teams(self) -> List[Dict]:
        """Get all MLB teams"""
        data = self.client.get_teams()
        if data.get("response"):
            return [self.mapper.map_team(t) for t in data["response"]]
        return []
    
    def close(self):
        """Close the client"""
        self.client.close()
    
    def close(self):
        """Close the client"""
        self.client.close()


class MLBFeatureEngine:
    """Generate features specific to MLB predictions"""
    
    def __init__(self, adapter: MLBAdapter):
        self.adapter = adapter
    
    def generate_pitcher_features(self, pitcher_id: int) -> Dict:
        """Generate features for a pitcher"""
        # Would fetch pitcher stats from database or API
        # Return standardized features
        return {
            "pitcher_id": pitcher_id,
            "role": "starter",  # or reliever
            "era": 0.0,
            "whip": 0.0,
            "strikeout_rate": 0.0,
            "walk_rate": 0.0,
            "home_run_rate": 0.0,
            "recent_era": 0.0,
            "vs_left_era": 0.0,
            "vs_right_era": 0.0,
        }
    
    def generate_bullpen_features(self, team_id: int, game_date: str) -> Dict:
        """Generate bullpen fatigue features"""
        return {
            "team_id": team_id,
            "pitch_count_today": 0,
            "relief_pitchers_used": 0,
            "high_leverage_pitches": 0,
            "consecutive_days_pitched": 0,
            "closer_available": True,
            "bullpen_exhausted": False,
        }
    
    def generate_handicap_features(
        self, 
        pitcher_id: int, 
        opponent_hand: str
    ) -> Dict:
        """Generate handedness split features"""
        return {
            "pitcher_id": pitcher_id,
            "opponent_hand": opponent_hand,
            "vs_hand_avg": 0.0,
            "advantage": 0.0,
        }
    
    def generate_park_features(self, venue_id: int) -> Dict:
        """Generate park factor features"""
        return {
            "venue_id": venue_id,
            "home_run_factor": 1.0,
            "run_factor": 1.0,
            "double_factor": 1.0,
            "is_hitter_friendly": False,
        }
    
    def generate_game_features(
        self, 
        home_pitcher_id: int, 
        away_pitcher_id: int,
        home_team_id: int,
        away_team_id: int,
        venue_id: int
    ) -> Dict:
        """Generate comprehensive game features"""
        return {
            "home_pitcher": self.generate_pitcher_features(home_pitcher_id),
            "away_pitcher": self.generate_pitcher_features(away_pitcher_id),
            "home_bullpen": self.generate_bullpen_features(home_team_id, ""),
            "away_bullpen": self.generate_bullpen_features(away_team_id, ""),
            "park": self.generate_park_features(venue_id),
            "home_offense_rating": 0.0,
            "away_offense_rating": 0.0,
        }


# Test the adapter
if __name__ == "__main__":
    print("=== Testing MLB Adapter ===\n")
    
    adapter = MLBAdapter()
    
    # Get today's games
    print("Today's MLB Games:")
    games = adapter.get_fixtures()
    for game in games:
        print(f"  {game['away_team']['name']} @ {game['home_team']['name']}")
        print(f"    Status: {game['status']}, Time: {game['start_time']}")
    
    # Get teams
    print("\n\nMLB Teams:")
    teams = adapter.client.get_teams()
    print(f"  Total: {len(teams)} teams")
    
    # Get probable pitchers
    print("\n\nProbable Pitchers (today):")
    pitchers = adapter.get_probable_pitchers(datetime.now().strftime("%Y-%m-%d"))
    for p in pitchers:
        home = p.get("home_pitcher", {}).get("fullName", "TBD")
        away = p.get("away_pitcher", {}).get("fullName", "TBD")
        print(f"  {away} @ {home}")
    
    adapter.close()
    print("\n\n[COMPLETE]")
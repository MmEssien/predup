"""
MLB Sport Adapter - Implements BaseSportAdapter interface
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any

from src.data.mlb_client import MLBStatsClient, MLBDataMapper
from src.data.sport_adapter import BaseSportAdapter


class MLBAdapter(BaseSportAdapter):
    """MLB adapter using StatsAPI"""
    
    sport_name = "mlb"
    league_name = "MLB"
    
    def __init__(self):
        self.client = MLBStatsClient()
        self.mapper = MLBDataMapper()
    
    def get_fixtures(self, date: Optional[str] = None, days_ahead: int = 1) -> List[Dict]:
        """Get upcoming MLB games"""
        if date is None:
            if days_ahead == 1:
                schedule = self.client.get_todays_games()
            else:
                games_data = self.client.get_upcoming_games(days_ahead)
                return [self.mapper.map_game(g) for g in games_data]
        else:
            schedule = self.client.get_schedule(date=date)
        
        results = []
        for date_obj in schedule.get("dates", []):
            for game in date_obj.get("games", []):
                results.append(self.mapper.map_game(game))
        
        return results
    
    def get_live_games(self) -> List[Dict]:
        """Get live MLB games"""
        # Could use the live feed endpoint
        schedule = self.client.get_todays_games()
        
        results = []
        for date_obj in schedule.get("dates", []):
            for game in date_obj.get("games", []):
                status = game.get("status", {}).get("abstractGameState")
                if status == "Live":
                    results.append(self.mapper.map_game(game))
        
        return results
    
    def get_team_stats(self, team_id: int) -> Dict:
        """Get team statistics"""
        team = self.client.get_team(team_id)
        if team:
            return self.mapper.map_team(team)
        return {}
    
    def get_odds(self, event_id: str, market: str = "moneyline") -> Dict:
        """Get betting odds for a game"""
        # MLB StatsAPI doesn't provide real odds
        # This would need to be integrated with a betting odds API
        # For now, return empty - will be implemented with odds API
        return {
            "sport": self.sport_name,
            "event_id": event_id,
            "market": market,
            "odds": {},
            "note": "Odds need separate betting API integration"
        }
    
    def get_game_details(self, event_id: str) -> Dict:
        """Get detailed game information"""
        try:
            game_pk = int(event_id)
            boxscore = self.client.get_game_boxscore(game_pk)
            if boxscore:
                return self.mapper.map_boxscore(boxscore)
        except Exception:
            pass
        return {}
    
    def get_probable_pitchers(self, date: str) -> List[Dict]:
        """Get probable pitchers for games on a date"""
        schedule = self.client.get_probable_pitchers(date)
        
        pitchers = []
        for date_obj in schedule.get("dates", []):
            for game in date_obj.get("games", []):
                home_pitcher = game.get("teams", {}).get("home", {}).get("probablePitcher")
                away_pitcher = game.get("teams", {}).get("away", {}).get("probablePitcher")
                
                pitchers.append({
                    "game_pk": game.get("gamePk"),
                    "home_pitcher": home_pitcher,
                    "away_pitcher": away_pitcher,
                })
        
        return pitchers
    
    def get_standings(self) -> Dict:
        """Get current standings"""
        return self.client.get_standings()
    
    def get_leaders(self, categories: List[str] = None) -> Dict:
        """Get league leaders"""
        if categories is None:
            categories = ["homeRuns", "runsBattedIn", "strikeouts"]
        return self.client.get_leaders(categories)
    
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
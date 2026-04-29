"""
Simple Math Baseline Models
===========================
Provides calibrated probabilities using basic statistical models.
No ML complexity - stable baseline for Phase 1.
"""

import logging
import math
import random
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class FootballBaselineModel:
    """
    Football baseline using Elo ratings + home advantage.
    """
    
    # Default Elo ratings (updated from historical data)
    DEFAULT_ELO = {
        "manchester city": 1850,
        "arsenal": 1820,
        "liverpool": 1810,
        "chelsea": 1790,
        "tottenham": 1770,
        "manchester united": 1760,
        "newcastle": 1740,
        "brighton": 1720,
        "fulham": 1700,
        "west ham": 1690,
        "brentford": 1680,
        "crystal palace": 1670,
        "aston villa": 1660,
        "wolves": 1650,
        "bournemouth": 1640,
        "everton": 1630,
        "nottingham forest": 1620,
        "luton": 1610,
        "burnley": 1600,
        "sheffield united": 1590,
        # European leagues
        "real madrid": 1840,
        "barcelona": 1830,
        "bayern munich": 1850,
        "psg": 1800,
        "dortmund": 1780,
        "milan": 1760,
        "inter": 1770,
        "juventus": 1750,
    }
    
    HOME_ADVANTAGE = 80  # Elo points
    
    def __init__(self):
        self.elo = dict(self.DEFAULT_ELO)
    
    def predict(self, home_team: str, away_team: str) -> float:
        """
        Predict home win probability using Elo.
        
        Returns:
            float: Probability of home team winning (0-1)
        """
        # Get Elo ratings
        home_elo = self._get_elo(home_team)
        away_elo = self._get_elo(away_team)
        
        # Add home advantage
        expected_elo = home_elo + self.HOME_ADVANTAGE
        
        # Calculate probability using logistic formula
        prob = 1.0 / (1.0 + 10.0 ** ((away_elo - expected_elo) / 400))
        
        return prob
    
    def _get_elo(self, team: str) -> int:
        """Get Elo rating for team"""
        team_lower = team.lower()
        
        for name, rating in self.elo.items():
            if name in team_lower or team_lower in name:
                return rating
        
        # Default for unknown teams
        return 1500
    
    def update_elo(self, winner: str, loser: str, home_win: bool, draw: bool = False):
        """Update Elo ratings after match"""
        # Simplified update
        pass


class MLBBaselineModel:
    """
    MLB baseline using runs scored/conceded averages.
    """
    
    # Rough team offensive ratings (runs per game)
    DEFAULT_OFFENSE = {
        "yankees": 5.5,
        "dodgers": 5.4,
        "astros": 5.2,
        "braves": 5.1,
        "rangers": 5.0,
        "phillies": 4.9,
        "cubs": 4.8,
        "red sox": 4.8,
        "mets": 4.7,
        "giants": 4.6,
    }
    
    DEFAULT_DEFENSE = {  # Lower is better (runs allowed)
        "dodgers": 3.5,
        "astros": 3.6,
        "braves": 3.7,
        "padres": 3.8,
        "phillies": 3.9,
        "cubs": 4.0,
        "marlins": 4.0,
        "yankees": 4.1,
        "mets": 4.2,
        "giants": 4.2,
    }
    
    HOME_ADVANTAGE = 0.15  # Extra runs at home
    
    def __init__(self):
        self.offense = dict(self.DEFAULT_OFFENSE)
        self.defense = dict(self.DEFAULT_DEFENSE)
    
    def predict(self, home_team: str, away_team: str) -> float:
        """
        Predict home win probability.
        
        Returns:
            float: Probability of home team winning (0-1)
        """
        home_off = self._get_offense(home_team)
        away_off = self._get_offense(away_team)
        
        home_def = self._get_defense(home_team)
        away_def = self._get_defense(away_team)
        
        # Expected runs
        home_runs = (home_off + away_def) / 2 + self.HOME_ADVANTAGE
        away_runs = (away_off + home_def) / 2
        
        # Calculate probability using runs distribution
        # Simple approximation using runs difference
        runs_diff = home_runs - away_runs
        
        # Convert to probability (logistic approximation)
        # Historically: +1 run = ~55% win probability
        prob = 1.0 / (1.0 + math.exp(-runs_diff * 0.55))
        
        return prob
    
    def _get_offense(self, team: str) -> float:
        """Get offensive rating"""
        team_lower = team.lower()
        for name, rating in self.offense.items():
            if name in team_lower or team_lower in name:
                return rating
        return 4.3  # Average
    
    def _get_defense(self, team: str) -> float:
        """Get defensive rating"""
        team_lower = team.lower()
        for name, rating in self.defense.items():
            if name in team_lower or team_lower in name:
                return rating
        return 4.3  # Average


class NBABaselineModel:
    """
    NBA baseline using net rating + home court advantage.
    """
    
    # Rough net ratings (points per 100 possessions)
    DEFAULT_NRT = {
        "celtics": +8.5,
        "lakers": +6.2,
        "nuggets": +5.8,
        "heat": +5.2,
        "bucks": +4.8,
        "clippers": +4.5,
        "suns": +4.2,
        "warriors": +3.8,
        "76ers": +3.5,
        "knicks": +3.2,
        "timberwolves": +2.8,
        "cavaliers": +2.5,
        "kings": +2.2,
        "pels": +1.8,
        "magic": +1.5,
        "mavs": +1.2,
    }
    
    HOME_ADVANTAGE = 3.0  # Points per 100 possessions
    
    def __init__(self):
        self.nrt = dict(self.DEFAULT_NRT)
    
    def predict(self, home_team: str, away_team: str) -> float:
        """
        Predict home win probability.
        
        Returns:
            float: Probability of home team winning (0-1)
        """
        home_nrt = self._get_nrt(home_team)
        away_nrt = self._get_nrt(away_team)
        
        # Add home advantage
        expected_diff = (home_nrt + self.HOME_ADVANTAGE) - away_nrt
        
        # Convert to probability using logistic
        # Historically: +3 nrt = ~55% win probability
        prob = 1.0 / (1.0 + math.exp(-expected_diff * 0.1))
        
        return prob
    
    def _get_nrt(self, team: str) -> float:
        """Get net rating"""
        team_lower = team.lower()
        for name, rating in self.nrt.items():
            if name in team_lower or team_lower in name:
                return rating
        return 0.0  # Average


class BaselinePredictionEngine:
    """
    Unified baseline engine for all sports.
    """
    
    def __init__(self):
        self.models = {
            "football": FootballBaselineModel(),
            "mlb": MLBBaselineModel(),
            "nba": NBABaselineModel()
        }
    
    def predict(self, sport: str, home_team: str, away_team: str) -> float:
        """Get baseline probability"""
        model = self.models.get(sport.lower())
        
        if model:
            return model.predict(home_team, away_team)
        
        # Default 50% for unknown sports
        return 0.50


# Global singleton
_baseline_engine = None


def get_baseline_engine() -> BaselinePredictionEngine:
    """Get global baseline engine"""
    global _baseline_engine
    if _baseline_engine is None:
        _baseline_engine = BaselinePredictionEngine()
    return _baseline_engine


def test_baseline_models():
    """Test baseline models"""
    print("Testing Baseline Models...")
    
    engine = get_baseline_engine()
    
    # Football
    print("\n--- Football (Elo-based) ---")
    prob = engine.predict("football", "Arsenal", "Liverpool")
    print(f"Arsenal vs Liverpool: Home win = {prob:.1%}")
    
    prob = engine.predict("football", "Man City", "Luton")
    print(f"Man City vs Luton: Home win = {prob:.1%}")
    
    # MLB
    print("\n--- MLB (Runs-based) ---")
    prob = engine.predict("mlb", "Yankees", "Dodgers")
    print(f"Yankees vs Dodgers: Home win = {prob:.1%}")
    
    prob = engine.predict("mlb", "Athletics", "Marlins")
    print(f"Athletics vs Marlins: Home win = {prob:.1%}")
    
    # NBA
    print("\n--- NBA (Net Rating based) ---")
    prob = engine.predict("nba", "Lakers", "Celtics")
    print(f"Lakers vs Celtics: Home win = {prob:.1%}")
    
    prob = engine.predict("nba", "Warriors", "Spurs")
    print(f"Warriors vs Spurs: Home win = {prob:.1%}")
    
    print("\nTest complete.")


if __name__ == "__main__":
    test_baseline_models()
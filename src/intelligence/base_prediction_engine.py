"""
Base Prediction Engine Interface
Unified architecture for all sports predictions
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime


@dataclass
class UnifiedPrediction:
    """Standardized prediction output across all sports"""
    sport: str
    fixture_id: str
    home_team: str
    away_team: str
    bet_on: str
    model_probability: float
    odds: float
    implied_probability: float
    edge: float
    ev: float
    ev_pct: float
    confidence: str
    start_time: str
    league: str
    
    def to_dict(self) -> Dict:
        return {
            "sport": self.sport,
            "fixture_id": self.fixture_id,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "bet_on": self.bet_on,
            "model_probability": self.model_probability,
            "odds": self.odds,
            "implied_probability": self.implied_probability,
            "edge": self.edge,
            "ev": self.ev,
            "ev_pct": self.ev_pct,
            "confidence": self.confidence,
            "start_time": self.start_time,
            "league": self.league,
        }


class BasePredictionEngine(ABC):
    """Abstract base class for all sport prediction engines"""
    
    sport_name: str = ""
    league_name: str = ""
    
    def __init__(self, api_key: Optional[str] = None, odds_adapter=None):
        self.api_key = api_key
        self.odds_adapter = odds_adapter
    
    @abstractmethod
    def get_fixtures(self, days_ahead: int = 1) -> List[Dict]:
        """Fetch upcoming fixtures"""
        pass
    
    @abstractmethod
    def build_features(self, fixture: Dict) -> Dict:
        """Build features for a fixture"""
        pass
    
    @abstractmethod
    def compute_probability(self, features: Dict) -> float:
        """Compute model probability from features"""
        pass
    
    def fetch_odds(self, home_team: str, away_team: str) -> Optional[Dict]:
        """Fetch odds for matchup"""
        if self.odds_adapter:
            return self.odds_adapter.get_odds(home_team, away_team)
        return None
    
    def compute_ev(
        self,
        model_prob: float,
        odds: float,
        implied_prob: float
    ) -> tuple:
        """Compute edge and expected value"""
        edge = model_prob - implied_prob
        ev = model_prob * (odds - 1) - (1 - model_prob)
        return edge, ev
    
    def determine_confidence(self, model_prob: float) -> str:
        """Determine confidence level"""
        diff = abs(model_prob - 0.5)
        if diff > 0.15:
            return "high"
        elif diff > 0.10:
            return "medium"
        return "low"
    
    def predict(self, fixture: Dict) -> Optional[UnifiedPrediction]:
        """Generate unified prediction for fixture"""
        # Build features
        features = self.build_features(fixture)
        
        # Compute probability
        model_prob = self.compute_probability(features)
        
        # Get teams
        home = fixture.get("home_team", "")
        away = fixture.get("away_team", "")
        fixture_id = str(fixture.get("id", ""))
        
        # Fetch odds
        odds_data = self.fetch_odds(home, away)
        
        if not odds_data or not odds_data.get("home_odds"):
            return None
        
        home_odds = odds_data.get("home_odds", 2.0)
        away_odds = odds_data.get("away_odds", 2.0)
        
        # Calculate implied probabilities
        implied_home = 1 / home_odds
        implied_away = 1 / away_odds
        total_implied = implied_home + implied_away
        
        # De-vig the market
        devig_home = implied_home / total_implied
        
        # Compute EV for both sides
        edge_home, ev_home = self.compute_ev(devig_home, home_odds, implied_home)
        edge_away, ev_away = self.compute_ev(1 - devig_home, away_odds, implied_away)
        
        # Choose best edge
        if ev_home >= ev_away:
            bet_on = "home"
            final_prob = devig_home
            final_odds = home_odds
            final_edge = edge_home
            final_ev = ev_home
            implied_prob = implied_home
        else:
            bet_on = "away"
            final_prob = 1 - devig_home
            final_odds = away_odds
            final_edge = edge_away
            final_ev = ev_away
            implied_prob = implied_away
        
        confidence = self.determine_confidence(final_prob)
        
        return UnifiedPrediction(
            sport=self.sport_name,
            fixture_id=fixture_id,
            home_team=home,
            away_team=away,
            bet_on=bet_on,
            model_probability=final_prob,
            odds=final_odds,
            implied_probability=implied_prob,
            edge=final_edge,
            ev=final_ev,
            ev_pct=final_ev * 100,
            confidence=confidence,
            start_time=fixture.get("start_time", ""),
            league=self.league_name
        )
    
    def predict_batch(self, fixtures: List[Dict]) -> List[UnifiedPrediction]:
        """Generate predictions for multiple fixtures"""
        predictions = []
        
        for fixture in fixtures:
            try:
                pred = self.predict(fixture)
                if pred:
                    predictions.append(pred)
            except Exception as e:
                continue
        
        return predictions


# Sport Registry
SPORTS_REGISTRY: Dict[str, type] = {}


def register_sport(sport_name: str):
    """Decorator to register a sport engine"""
    def decorator(cls):
        SPORTS_REGISTRY[sport_name] = cls
        return cls
    return decorator


def get_engine(sport_name: str, **kwargs) -> Optional[BasePredictionEngine]:
    """Get engine instance for sport"""
    if sport_name in SPORTS_REGISTRY:
        return SPORTS_REGISTRY[sport_name](**kwargs)
    return None


def list_registered_sports() -> List[str]:
    """List all registered sports"""
    return list(SPORTS_REGISTRY.keys())
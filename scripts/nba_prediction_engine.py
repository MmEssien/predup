"""NBA Live Prediction Engine

Run live predictions on upcoming NBA games.
Fetches data, generates features, runs model, calculates EV.

Usage:
    python scripts/nba_prediction_engine.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from datetime import datetime
from typing import Dict, List, Optional
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class NBAPredictionEngine:
    """Live NBA prediction engine"""
    
    def __init__(self, model=None, odds_api_key: Optional[str] = None):
        self.model = model
        self.odds_api_key = odds_api_key
        
        # Threshold for betting (configurable)
        self.min_edge = 0.03
        self.min_probability = 0.55
    
    def fetch_upcoming_games(self, days_ahead: int = 1) -> List[Dict]:
        """Fetch upcoming NBA games"""
        from src.data.nba_adapter import NBAAdapter
        
        adapter = NBAAdapter()
        games = adapter.get_fixtures(days_ahead=days_ahead)
        adapter.close()
        
        return games
    
    def fetch_team_stats(self) -> Dict[int, Dict]:
        """Fetch current team statistics"""
        from src.data.nba_adapter import NBAAdapter
        
        adapter = NBAAdapter()
        teams = adapter.get_teams()
        standings = adapter.get_standings()
        adapter.close()
        
        # Build stats dict from standings
        stats = {}
        for s in standings:
            team_id = s.get("team_id")
            if team_id:
                stats[team_id] = {
                    "team_id": team_id,
                    "team_name": s.get("team_name", ""),
                    "wins": s.get("win", 0),
                    "losses": s.get("loss", 0),
                    "win_home": s.get("win_home", 0),
                    "loss_home": s.get("loss_home", 0),
                    "win_away": s.get("win_away", 0),
                    "loss_away": s.get("loss_away", 0),
                    "points_for": s.get("points_for", 0),
                    "points_against": s.get("points_against", 0),
                    "win_last_10": s.get("win_last_10", 0),
                    "streak": s.get("streak", ""),
                }
        
        return stats
    
    def fetch_odds(self, games: List[Dict]) -> Dict:
        """Fetch real betting odds from Odds API"""
        from src.data.odds_client import OddsApiClient
        
        odds_data = {}
        
        try:
            client = OddsApiClient(api_key=self.odds_api_key)
            
            for game in games:
                event_id = game.get("event_id")
                home_team = game.get("home_team", {}).get("name", "")
                away_team = game.get("away_team", {}).get("name", "")
                
                # Get NBA moneyline odds
                odds = client.get_odds(
                    sport="basketball_nba",
                    market="h2h"
                )
                
                # Match odds to games
                for o in odds:
                    if self._match_teams(o, home_team, away_team):
                        odds_data[event_id] = o
            
            client.close()
            
        except Exception as e:
            logger.warning(f"Could not fetch odds: {e}")
            logger.info("Using fallback simulated odds")
        
        return odds_data
    
    def _match_teams(self, odds: Dict, home: str, away: str) -> bool:
        """Match odds record to game"""
        teams = odds.get("teams", [])
        if len(teams) >= 2:
            return (home.lower() in teams[0].lower() and away.lower() in teams[1].lower())
        return False
    
    def generate_predictions(
        self,
        games: List[Dict],
        team_stats: Dict,
        standings: List[Dict],
        odds: Dict
    ) -> List[Dict]:
        """Generate predictions for all games"""
        
        from src.features.nba_features import NBAFeatureEngine
        from src.models.nba_model import NBAEVEngine
        
        engine = NBAFeatureEngine()
        ev_engine = NBAEVEngine(self.model) if self.model else None
        
        predictions = []
        
        for game in games:
            home_team_id = game.get("home_team", {}).get("id")
            away_team_id = game.get("away_team", {}).get("id")
            home_team_name = game.get("home_team", {}).get("name", "?")
            away_team_name = game.get("away_team", {}).get("name", "?")
            event_id = game.get("event_id")
            
            # Get team stats
            home_stats = team_stats.get(home_team_id, {})
            away_stats = team_stats.get(away_team_id, {})
            
            # Get odds
            game_odds = odds.get(event_id, {})
            ml = game_odds.get("markets", {}).get("h2h", {})
            home_odds = ml.get("home_odds")
            away_odds = ml.get("away_odds")
            
            # Generate features
            features = engine.generate_all_features(
                home_team_id=home_team_id,
                away_team_id=away_team_id,
                home_stats=home_stats,
                away_stats=away_stats,
                standings=standings,
                home_odds=home_odds,
                away_odds=away_odds,
                game_date=datetime.fromisoformat(game.get("start_time", datetime.now().isoformat()))
            )
            
            # Calculate prediction
            if self.model and hasattr(self.model, "predict"):
                prediction = self.model.predict(game, team_stats, standings, game_odds, None)
            else:
                # Use simple model-based prediction
                home_prob = self._simple_prediction(features)
                edge = self._calculate_edge(home_prob, home_odds)
                prediction = {
                    "home_win_prob": home_prob,
                    "away_win_prob": 1 - home_prob,
                    "edge": edge,
                    "expected_value": edge * home_odds if home_odds else 0,
                    "decision": "no_bet" if edge < self.min_edge else "bet_home",
                    "confidence": "high" if abs(home_prob - 0.5) > 0.15 else "medium"
                }
            
            # Format result
            predictions.append({
                "event_id": event_id,
                "home_team": home_team_name,
                "away_team": away_team_name,
                "start_time": game.get("start_time"),
                "prediction": prediction,
                "odds": {
                    "home": home_odds,
                    "away": away_odds
                },
                "bet_decision": self._make_bet_decision(prediction, home_odds, away_odds)
            })
        
        return predictions
    
    def _simple_prediction(self, features: Dict) -> float:
        """Simple heuristic-based prediction"""
        
        # Base probability from win percentages
        home_win_pct = features.get("home_win_pct", 0.5)
        away_win_pct = features.get("away_win_pct", 0.5)
        
        # Adjust for rest advantage
        rest_adj = features.get("rest_advantage", 0) * 0.02
        
        # Adjust for form
        form_adj = features.get("home_form_advantage", 0) * 0.05
        
        # Adjust for injuries
        injury_adj = features.get("injury_impact_diff", 0) * 0.1
        
        home_prob = 0.5 + (home_win_pct - 0.5) * 0.5 + rest_adj + form_adj + injury_adj
        
        return max(0.1, min(0.9, home_prob))
    
    def _calculate_edge(self, probability: float, odds: float) -> float:
        """Calculate edge from probability and odds"""
        if not odds or odds <= 0:
            return 0
        implied = 1 / odds
        return probability - implied
    
    def _make_bet_decision(
        self,
        prediction: Dict,
        home_odds: Optional[float],
        away_odds: Optional[float]
    ) -> Dict:
        """Make final bet decision"""
        
        home_prob = prediction.get("home_win_prob", 0.5)
        away_prob = 1 - home_prob
        home_edge = prediction.get("edge", self._calculate_edge(home_prob, home_odds))
        away_edge = prediction.get("edge", self._calculate_edge(away_prob, away_odds))
        
        # Check home bet
        if home_edge >= self.min_edge and home_prob >= self.min_probability:
            return {
                "action": "bet_home",
                "odds": home_odds,
                "edge": home_edge,
                "ev": home_prob * (home_odds - 1) - (1 - home_prob) if home_odds else 0,
                "stake_pct": 0.01  # 1% of bankroll
            }
        
        # Check away bet
        if away_edge >= self.min_edge and away_prob >= self.min_probability:
            return {
                "action": "bet_away",
                "odds": away_odds,
                "edge": away_edge,
                "ev": away_prob * (away_odds - 1) - (1 - away_prob) if away_odds else 0,
                "stake_pct": 0.01
            }
        
        return {
            "action": "no_bet",
            "odds": None,
            "edge": 0,
            "ev": 0,
            "stake_pct": 0,
            "reason": "below_threshold"
        }
    
    def format_prediction(self, predictions: List[Dict]) -> str:
        """Format predictions for display"""
        
        output = []
        output.append("=" * 60)
        output.append("NBA PREDICTION REPORT")
        output.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        output.append("=" * 60)
        
        qualifying_bets = [p for p in predictions if p["bet_decision"]["action"] != "no_bet"]
        
        if not qualifying_bets:
            output.append("\nNo qualifying bets today.")
            output.append(f"Min edge: {self.min_edge:.1%}, Min prob: {self.min_probability:.1%}")
        else:
            output.append(f"\nQUALIFYING BETS ({len(qualifying_bets)}):")
            output.append("-" * 60)
            
            for p in qualifying_bets:
                decision = p["bet_decision"]
                output.append("")
                output.append(f"{p['away_team']} @ {p['home_team']}")
                output.append(f"  Time: {p['start_time']}")
                output.append(f"  Action: {decision['action'].upper()}")
                output.append(f"  Odds: {decision['odds']}")
                output.append(f"  Edge: {decision['edge']:.2%}")
                output.append(f"  EV: {decision['ev']:.4f}")
                output.append(f"  Stake: {decision['stake_pct']:.1%} of bankroll")
        
        output.append("")
        output.append(f"All games analyzed: {len(predictions)}")
        
        return "\n".join(output)


def main():
    """Run NBA prediction engine"""
    
    logger.info("=== Starting NBA Prediction Engine ===")
    
    engine = NBAPredictionEngine()
    
    # Fetch data
    logger.info("Fetching upcoming games...")
    games = engine.fetch_upcoming_games(days_ahead=1)
    logger.info(f"Found {len(games)} upcoming games")
    
    if not games:
        logger.warning("No upcoming games found")
        return
    
    logger.info("Fetching team stats...")
    team_stats = engine.fetch_team_stats()
    
    # Fetch odds (may fail without API key)
    logger.info("Fetching odds...")
    try:
        odds = engine.fetch_odds(games)
    except Exception as e:
        logger.warning(f"Odds fetch failed: {e}")
        odds = {}
    
    # Generate predictions
    logger.info("Generating predictions...")
    predictions = engine.generate_predictions(games, team_stats, [], odds)
    
    # Format output
    report = engine.format_prediction(predictions)
    print(report)
    
    # Save to file
    output_file = Path("nba_predictions.json")
    with open(output_file, "w") as f:
        json.dump(predictions, f, indent=2, default=str)
    
    logger.info(f"Predictions saved to {output_file}")
    
    return predictions


if __name__ == "__main__":
    main()
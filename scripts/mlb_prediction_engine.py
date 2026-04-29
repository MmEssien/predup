"""
MLB Prediction Engine Integration
Complete MLB betting system with predictions, odds, and EV analysis
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from datetime import datetime
from typing import List, Dict, Optional
import logging
import numpy as np

from src.data.mlb_adapter import MLBAdapter, MLBFeatureEngine
from src.data.mlb_client import MLBStatsClient
from src.intelligence.mlb_intelligence import (
    MLBOddsSimulator,
    MLBIntelligenceEngine,
    MLBCalibrator
)
import warnings
warnings.filterwarnings('ignore')

logger = logging.getLogger(__name__)


class MLBPredictionEngine:
    """
    Complete MLB prediction and betting engine
   Combines:
    - MLB data via adapter
    - Feature engineering
    - Odds generation 
    - EV calculations
    - Bet recommendations
    """
    
    def __init__(self, use_live_odds: bool = False):
        # Data adapters
        self.adapter = MLBAdapter()
        self.feature_engine = MLBFeatureEngine(self.adapter)
        
        # Intelligence components
        self.odds_simulator = MLBOddsSimulator()
        self.intel_engine = MLBIntelligenceEngine(use_api=use_live_odds)
        self.calibrator = MLBCalibrator()
        
        # Configuration
        self.moneyline_threshold = 0.52  # Need 52%+ win prob to bet
        self.total_threshold = 0.55  # Need 55%+ for over
        self.min_ev_pct = 5.0  # Minimum 5% EV to bet
        
    def get_predictions(self, days_ahead: int = 1) -> List[Dict]:
        """
        Get all predictions for upcoming games
        
        Returns list of predictions with:
        - Game info
        - Model probabilities
        - Odds
        - EV analysis
        - Bet recommendations
        """
        # Get upcoming games
        games = self.adapter.get_fixtures(days_ahead=days_ahead)
        
        predictions = []
        
        for game in games:
            try:
                pred = self._generate_prediction(game)
                if pred:
                    predictions.append(pred)
            except Exception as e:
                logger.warning(f"Failed to generate prediction for {game.get('event_id')}: {e}")
        
        return predictions
    
    def get_live_predictions(self) -> List[Dict]:
        """Get predictions for live games with in-play odds"""
        live_games = self.adapter.get_live_games()
        
        predictions = []
        for game in live_games:
            try:
                pred = self._generate_prediction(game, live=True)
                if pred:
                    predictions.append(pred)
            except Exception as e:
                logger.warning(f"Failed: {e}")
        
        return predictions
    
    def _generate_prediction(self, game: Dict, live: bool = False) -> Optional[Dict]:
        """Generate single prediction"""
        # Extract game info
        home_team = game.get("home_team", {})
        away_team = game.get("away_team", {})
        
        home_name = home_team.get("name", "Unknown")
        away_name = away_team.get("name", "Unknown")
        
        # Get probable pitchers (if available)
        pitcher_info = self._get_pitcher_info(game.get("event_id"))
        
        # Generate model probabilities
        # In real implementation, this would use trained model
        # For now, use team-based estimate
        model_home_prob, model_away_prob = self._estimate_win_probability(
            home_team, away_team, pitcher_info
        )
        
        # Generate odds (simulated for backtest, real in production)
        ml_odds = self.odds_simulator.generate_moneyline_odds(
            model_home_prob, model_away_prob, home_name, away_name
        )
        
        totals = self.odds_simulator.generate_totals_odds(
            0.50, np.random.choice([7.0, 7.5, 8.0, 8.5, 9.0])
        )  # Simplified - real impl would use model
        
        # EV Analysis
        home_ev = self.intel_engine.calculate_ev(model_home_prob, ml_odds['home_ml'])
        away_ev = self.intel_engine.calculate_ev(model_away_prob, ml_odds['away_ml'])
        over_ev = self.intel_engine.calculate_ev(0.55, totals['over_odds'])
        
        # Combine into single prediction
        prediction = {
            "sport": "mlb",
            "event_id": game.get("event_id"),
            "game": f"{away_name} @ {home_name}",
            "start_time": game.get("start_time"),
            "status": game.get("status"),
            "venue": game.get("venue"),
            
            # Probabilities
            "home_win_prob": model_home_prob,
            "away_win_prob": model_away_prob,
            
            # Odds
            "odds": {
                "home_ml": ml_odds['home_ml'],
                "away_ml": ml_odds['away_ml'],
                "over": totals['over_odds'],
                "under": totals['under_odds'],
                "total_line": totals['total_line']
            },
            
            # Market implied
            "implied": {
                "home": ml_odds['implied_home'],
                "away": ml_odds['implied_away'],
                "over": totals['implied_over'],
                "under": totals['implied_under']
            },
            
            # EV Analysis
            "ev": {
                "home": home_ev,
                "away": away_ev,
                "over": over_ev
            },
            
            # Recommended bets
            "recommendations": self._get_recommendations(
                model_home_prob, model_away_prob, ml_odds, totals
            ),
            
            # Pitcher info
            "pitchers": pitcher_info,
            
            # Model metadata
            "generated_at": datetime.utcnow().isoformat(),
            "live": live
        }
        
        return prediction
    
    def _estimate_win_probability(
        self, 
        home_team: Dict, 
        away_team: Dict,
        pitcher_info: Dict
    ) -> tuple:
        """
        Estimate win probability
        
        In production, this would use:
        - Trained ML model
        - Pitcher adjustments
        - Bullpen factors
        - Recent form
        """
        # Simplified: use win record as proxy
        home_record = home_team.get("record", "0-0")
        away_record = away_team.get("record", "0-0") 
        
        # Parse record to get win %
        try:
            home_w, home_l = map(int, home_record.split("-"))
            home_pct = home_w / max(1, home_w + home_l)
        except:
            home_pct = 0.5
        
        try:
            away_w, away_l = map(int, away_record.split("-"))
            away_pct = away_w / max(1, away_w + away_l)
        except:
            away_pct = 0.5
        
        # Adjust for home field advantage (~3%)
        home_pct += 0.03
        away_pct = 1 - home_pct
        
        return home_pct, away_pct
    
    def _get_pitcher_info(self, event_id: str) -> Dict:
        """Get pitcher information for game"""
        # Get probable pitchers from API
        try:
            pitchers = self.adapter.get_probable_pitchers(
                datetime.now().strftime("%Y-%m-%d")
            )
            
            for p in pitchers:
                if str(p.get("game_pk")) == event_id:
                    return {
                        "home_pitcher": p.get("home_pitcher", {}),
                        "away_pitcher": p.get("away_pitcher", {})
                    }
        except:
            pass
        
        return {"home_pitcher": None, "away_pitcher": None}
    
    def _get_recommendations(
        self,
        home_prob: float,
        away_prob: float,
        ml_odds: Dict,
        totals: Dict
    ) -> List[Dict]:
        """Generate bet recommendations"""
        recommendations = []
        
        # Home moneyline
        home_bet = self.intel_engine.analyze_bet(home_prob, ml_odds['home_ml'], self.moneyline_threshold)
        if home_bet["recommendation"] in ["BET", "BET LARGE"]:
            recommendations.append({
                "market": "moneyline",
                "selection": "home",
                "team": ml_odds["home_team"],
                "odds": ml_odds["home_ml"],
                "prob": home_prob,
                "ev": home_bet["ev_pct"],
                "recommendation": home_bet["recommendation"],
                "reason": home_bet["reason"]
            })
        
        # Away moneyline
        away_bet = self.intel_engine.analyze_bet(away_prob, ml_odds['away_ml'], self.moneyline_threshold)
        if away_bet["recommendation"] in ["BET", "BET LARGE"]:
            recommendations.append({
                "market": "moneyline",
                "selection": "away",
                "team": ml_odds["away_team"],
                "odds": ml_odds["away_ml"],
                "prob": away_prob,
                "ev": away_bet["ev_pct"],
                "recommendation": away_bet["recommendation"],
                "reason": away_bet["reason"]
            })
        
        return recommendations
    
    def get_todays_recommendations(self) -> List[Dict]:
        """Get today's recommended bets"""
        predictions = self.get_predictions(days_ahead=1)
        
        all_bets = []
        for pred in predictions:
            bets = pred.get("recommendations", [])
            for bet in bets:
                bet["game"] = pred["game"]
                bet["start_time"] = pred["start_time"]
                all_bets.append(bet)
        
        return all_bets
    
    def print_todays_bets(self):
        """Print today's recommended bets"""
        bets = self.get_todays_recommendations()
        
        print("="*80)
        print("  MLB BETTING RECOMMENDATIONS")
        print(f"  {datetime.now().strftime('%Y-%m-%d')}")
        print("="*80)
        
        if not bets:
            print("\nNo qualifying bets today.")
            print("\nReason: No games with sufficient edge (>5% EV)")
            return
        
        print(f"\n{len(bets)} qualifying bets:")
        
        for i, bet in enumerate(bets, 1):
            print(f"\n{i}. {bet['market'].upper()}: {bet['selection']} ({bet['team']})")
            print(f"   Game: {bet['game']}")
            print(f"   Odds: {bet['odds']}")
            print(f"   Model Prob: {bet['prob']:.1%}")
            print(f"   EV: {bet['ev']:+.1f}%")
            print(f"   {bet['reason']}")
        
        # Summary
        total_ev = sum(b["ev"] for b in bets)
        print(f"\n{'='*60}")
        print(f"  TOTAL EXPECTED VALUE: {total_ev:+.1f}%")
        print(f"{'='*60}")
    
    def close(self):
        """Clean up resources"""
        self.adapter.close()
        self.intel_engine.close()


if __name__ == "__main__":
    engine = MLBPredictionEngine()
    
    print("="*80)
    print("  MLB PREDICTION ENGINE - LIVE TEST")
    print("="*80)
    
    # Get today's games
    predictions = engine.get_predictions()
    
    print(f"\nFound {len(predictions)} games today\n")
    
    # Show first prediction as example
    if predictions:
        p = predictions[0]
        print("Example Game:")
        print(f"  {p['game']}")
        print(f"  Home Win Prob: {p['home_win_prob']:.1%}")
        print(f"  Home Odds: {p['odds']['home_ml']}")
        print(f"  Home EV: {p['ev']['home']['ev_pct']:+.1f}%")
        print(f"  Recommendations: {len(p['recommendations'])}")
    
    # Print recommendations
    engine.print_todays_bets()
    
    engine.close()
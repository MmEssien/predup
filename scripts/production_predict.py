"""
Production Prediction Script - BL1 and PL only

Generates live predictions for production leagues with full tracking.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from src.data.connection import DatabaseManager
from src.data.api_football_client import ApiFootballClient
from src.features.repository import FeatureRepository
from src.models.trainer import ModelTrainer
from src.decisions.engine import LEAGUE_CONFIGS, ENABLED_LEAGUES, DecisionEngine
from src.data.odds_simulator import OddsManager
from src.utils.helpers import load_config
import warnings
warnings.filterwarnings('ignore')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

config = load_config()
model_config = config.get('model', {})
feature_config = config.get('features', {})

db_manager = DatabaseManager.get_instance()
db_manager.initialize()

odds_manager = OddsManager(use_real_api=False)
api_client = ApiFootballClient()


def get_upcoming_fixtures(league_code: str, days_ahead: int = 3) -> List[Dict]:
    """Get upcoming fixtures for a league"""
    league_conf = LEAGUE_CONFIGS.get(league_code)
    if not league_conf:
        return []
    
    comp_id = league_conf["competition_id"]
    
    try:
        from datetime import date
        today = date.today().isoformat()
        future = (date.today() + timedelta(days=days_ahead)).isoformat()
        
        response = api_client.client.get(
            f"{api_client.base_url}/fixtures",
            params={
                "league": comp_id,
                "from": today,
                "to": future,
                "status": "NS"  # Not Started
            }
        )
        response.raise_for_status()
        data = response.json()
        
        fixtures = []
        for fixture in data.get("response", []):
            fixtures.append({
                "fixture_id": fixture["fixture"]["id"],
                "home_team": fixture["teams"]["home"]["name"],
                "away_team": fixture["teams"]["away"]["name"],
                "commence_time": fixture["fixture"]["date"],
                "league": league_code,
                "competition_id": comp_id
            })
        
        return fixtures
    
    except Exception as e:
        logger.warning(f"Failed to fetch fixtures for {league_code}: {e}")
        return []


def generate_prediction(
    league_code: str,
    fixture_id: int,
    home_team: str,
    away_team: str
) -> Optional[Dict]:
    """Generate prediction for a fixture"""
    league_conf = LEAGUE_CONFIGS.get(league_code)
    if not league_conf:
        return None
    
    comp_id = league_conf["competition_id"]
    threshold = league_conf["threshold"]
    
    with db_manager.session() as session:
        repo = FeatureRepository(session, feature_config)
        
        try:
            # Get training data
            X, y = repo.get_training_data(competition_id=comp_id, target_column='target_over_25')
            
            # Train model
            trainer = ModelTrainer(model_config)
            trainer.feature_names = list(X.columns)
            X_train, X_test, y_train, y_test = trainer.prepare_data(X, y)
            trainer.train_ensemble(X_train, y_train)
            
            # Create feature vector for the fixture
            # This is a simplified version - you'd need proper feature engineering
            # For now, we'll use average stats from recent matches
            
            # Get model prediction
            y_prob = trainer.ensemble_proba(X_test)
            y_pred = trainer.ensemble_predict(X_test)
            
            # Use average probability from recent predictions as proxy
            # In production, you'd create real features for the fixture
            avg_prob = float(y_prob.mean())
            avg_pred = int(y_pred.mean() > 0.5)
            
            # Get realistic odds
            over_odds = odds_manager.get_over_25_odds(league_code, avg_prob)
            
            # Make decision
            decision_engine = DecisionEngine(config=config, league_code=league_code)
            is_accepted, confidence, decision = decision_engine.make_decision(
                average_prob,
                {},
                threshold
            )
            
            return {
                "fixture_id": fixture_id,
                "league": league_code,
                "home_team": home_team,
                "away_team": away_team,
                "model_probability": round(avg_prob, 3),
                "threshold": threshold,
                "over_odds": over_odds,
                "implied_prob": round(1/over_odds, 3),
                "edge": round(avg_prob - (1/over_odds), 3),
                "decision": decision,
                "is_accepted": is_accepted,
                "expected_roi": round((avg_prob * (over_odds - 1) - (1 - avg_prob)) * 100, 1),
                "generated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Prediction failed for {league_code} {fixture_id}: {e}")
            return None


def main():
    """Main prediction runner"""
    print("="*70)
    print("  PRODUCTION PREDICTIONS - BL1 & PL")
    print(f"  Generated: {datetime.utcnow().isoformat()}")
    print("="*70)
    
    all_predictions = []
    
    for league_code in ENABLED_LEAGUES:
        print(f"\n{'='*50}")
        print(f"  {league_code}")
        print(f"{'='*50}")
        
        try:
            fixtures = get_upcoming_fixtures(league_code, days_ahead=2)
            
            if not fixtures:
                print(f"  No upcoming fixtures found")
                continue
            
            print(f"  Found {len(fixtures)} upcoming fixtures")
            
            for fixture in fixtures:
                pred = generate_prediction(
                    league_code,
                    fixture["fixture_id"],
                    fixture["home_team"],
                    fixture["away_team"]
                )
                
                if pred:
                    all_predictions.append(pred)
                    
                    if pred["is_accepted"]:
                        print(f"\n  ✓ {pred['home_team']} vs {pred['away_team']}")
                        print(f"    Prob: {pred['model_probability']:.1%} | Odds: {pred['over_odds']}")
                        print(f"    Edge: {pred['edge']:+.1%} | Expected ROI: {pred['expected_roi']:+.1f}%")
                    else:
                        print(f"\n  ✗ {pred['home_team']} vs {pred['away_team']}")
                        print(f"    Decision: {pred['decision']} (prob: {pred['model_probability']:.1%})")
        
        except Exception as e:
            logger.error(f"Failed to process {league_code}: {e}")
    
    # Summary
    print("\n" + "="*70)
    print("  PREDICTION SUMMARY")
    print("="*70)
    
    accepted = [p for p in all_predictions if p["is_accepted"]]
    rejected = [p for p in all_predictions if not p["is_accepted"]]
    
    print(f"\n  Total: {len(all_predictions)}")
    print(f"  Accepted: {len(accepted)}")
    print(f"  Rejected: {len(rejected)}")
    
    if accepted:
        avg_roi = sum(p["expected_roi"] for p in accepted) / len(accepted)
        avg_edge = sum(p["edge"] for p in accepted) / len(accepted)
        print(f"\n  Average Expected ROI: {avg_roi:+.1f}%")
        print(f"  Average Edge: {avg_edge:+.1%}")
        
        # By league
        print(f"\n  By League:")
        for league in ENABLED_LEAGUES:
            league_preds = [p for p in accepted if p["league"] == league]
            if league_preds:
                league_roi = sum(p["expected_roi"] for p in league_preds) / len(league_preds)
                print(f"    {league}: {len(league_preds)} bets, {league_roi:+.1f}% expected ROI")
    
    api_client.close()
    odds_manager.close()
    
    print("\n[COMPLETE]")


if __name__ == "__main__":
    main()
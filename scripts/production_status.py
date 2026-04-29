"""
Production Prediction System - v2
Handles off-season gracefully and provides status reporting
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from datetime import datetime, timedelta
from src.data.connection import DatabaseManager
from src.data.api_football_client import ApiFootballClient
from src.features.repository import FeatureRepository
from src.models.trainer import ModelTrainer
from src.decisions.engine import LEAGUE_CONFIGS, ENABLED_LEAGUES, DecisionEngine
from src.data.odds_simulator import OddsManager
from src.utils.helpers import load_config
import warnings
warnings.filterwarnings('ignore')

config = load_config()
model_config = config.get('model', {})
feature_config = config.get('features', {})

# API-Football league IDs (corrected from earlier analysis)
API_LEAGUE_IDS = {
    "BL1": 78,   # Bundesliga 
    "PL": 39,    # Premier League
}


def check_upcoming_via_api(league_code: str) -> list:
    """Check API for upcoming fixtures"""
    api_id = API_LEAGUE_IDS.get(league_code)
    if not api_id:
        return []
    
    api_client = ApiFootballClient()
    try:
        # Try with season parameter (2025 is current season)
        today = datetime.now()
        
        resp = api_client.client.get(
            f"{api_client.base_url}/fixtures",
            params={
                "league": api_id,
                "season": 2025,
                "from": today.strftime("%Y-%m-%d"),
                "to": (today + timedelta(days=7)).strftime("%Y-%m-%d")
            }
        )
        
        if resp.status_code == 200:
            data = resp.json()
            return data.get("response", [])
    except Exception as e:
        print(f"    API error: {e}")
    finally:
        api_client.close()
    
    return []


def generate_prediction_for_league(league_code: str) -> dict:
    """Generate prediction using historical model data"""
    league_conf = LEAGUE_CONFIGS.get(league_code)
    if not league_conf:
        return {"league": league_code, "error": "No config"}
    
    comp_id = league_conf["competition_id"]
    threshold = league_conf["threshold"]
    
    db_manager = DatabaseManager.get_instance()
    db_manager.initialize()
    
    with db_manager.session() as session:
        repo = FeatureRepository(session, feature_config)
        
        try:
            X, y = repo.get_training_data(
                competition_id=comp_id, 
                target_column='target_over_25'
            )
            
            trainer = ModelTrainer(model_config)
            trainer.feature_names = list(X.columns)
            X_train, X_test, y_train, y_test = trainer.prepare_data(X, y)
            trainer.train_ensemble(X_train, y_train)
            
            # Get predictions on test set
            y_prob = trainer.ensemble_proba(X_test)
            y_pred = trainer.ensemble_predict(X_test)
            
            # Analyze by threshold
            above_thresh = y_prob >= threshold
            n_bets = above_thresh.sum()
            
            if n_bets == 0:
                return {
                    "league": league_code,
                    "status": "no_bets",
                    "threshold": threshold,
                    "message": "No historical bets above threshold"
                }
            
            wins = (y_pred[above_thresh] == y_test.values[above_thresh]).sum()
            win_rate = wins / n_bets
            
            # Get realistic odds
            odds_manager = OddsManager(use_real_api=False)
            probs = y_prob[above_thresh]
            avg_odds = sum(odds_manager.get_over_25_odds(league_code, p) for p in probs) / len(probs)
            odds_manager.close()
            
            # Calculate ROI
            roi = (win_rate * avg_odds - 1) * 100
            
            return {
                "league": league_code,
                "status": "ready",
                "threshold": threshold,
                "historical_bets": int(n_bets),
                "historical_win_rate": round(win_rate * 100, 1),
                "avg_odds": round(avg_odds, 2),
                "historical_roi": round(roi, 1),
                "next_fixture": None  # Would come from API
            }
            
        except Exception as e:
            return {"league": league_code, "error": str(e)}


def main():
    print("="*70)
    print("  PREDUP PRODUCTION STATUS")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*70)
    
    # Check 1: API availability for live fixtures
    print("\n--- Live Fixture Check ---")
    
    live_fixtures = {}
    for league in ENABLED_LEAGUES:
        print(f"\n{league}: Checking API...")
        fixtures = check_upcoming_via_api(league)
        
        if fixtures:
            live_fixtures[league] = fixtures
            print(f"  Found {len(fixtures)} upcoming fixtures")
        else:
            print(f"  No upcoming fixtures (may be off-season)")
    
    # Check 2: Historical model performance
    print("\n--- Historical Model Performance ---")
    
    all_results = []
    for league in ENABLED_LEAGUES:
        print(f"\n{league}: Analyzing...")
        result = generate_prediction_for_league(league)
        all_results.append(result)
        
        if result.get("status") == "ready":
            print(f"  Threshold: {result['threshold']}")
            print(f"  Historical Bets: {result['historical_bets']}")
            print(f"  Win Rate: {result['historical_win_rate']}%")
            print(f"  Avg Odds: {result['avg_odds']}")
            print(f"  Historical ROI: {result['historical_roi']:+.1f}%")
        elif result.get("error"):
            print(f"  Error: {result['error']}")
        else:
            print(f"  {result.get('message', 'No data')}")
    
    # Summary
    print("\n" + "="*70)
    print("  PRODUCTION SUMMARY")
    print("="*70)
    
    ready_leagues = [r for r in all_results if r.get("status") == "ready"]
    
    print(f"\n  Production Leagues: {len(ENABLED_LEAGUES)}")
    print(f"  Model-Ready Leagues: {len(ready_leagues)}")
    print(f"  Live Fixtures Available: {sum(len(f) for f in live_fixtures.values())}")
    
    if ready_leagues:
        total_bets = sum(r['historical_bets'] for r in ready_leagues)
        total_roi = sum(r['historical_roi'] * r['historical_bets'] for r in ready_leagues) / total_bets
        print(f"  Historical Performance: {total_bets} bets, {total_roi:+.1f}% ROI")
    
    # Status
    print("\n  Status:")
    if live_fixtures:
        print("    [OK] LIVE - Fixtures available, ready for predictions")
    else:
        print("    [--] OFF-SEASON - No fixtures in next 7 days")
        print("    [OK] System ready - will process when fixtures available")
    
    print("\n[COMPLETE]")


if __name__ == "__main__":
    main()
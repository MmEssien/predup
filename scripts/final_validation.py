"""
Final comprehensive test with validation for promoted leagues
Also test ELC/ECD/POR with different data availability check
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import numpy as np
import pandas as pd
from datetime import datetime

from src.data.connection import DatabaseManager
from src.features.repository import FeatureRepository
from src.models.trainer import ModelTrainer
from src.decisions.engine import LEAGUE_CONFIGS
from src.data.odds_simulator import OddsManager
from src.utils.helpers import load_config
import warnings
warnings.filterwarnings('ignore')

config = load_config()
model_config = config.get('model', {})

db_manager = DatabaseManager.get_instance()
db_manager.initialize()

odds_manager = OddsManager(use_real_api=False)

# All configured leagues
ALL_LEAGUES = list(LEAGUE_CONFIGS.keys())

print("="*80)
print("  FINAL COMPREHENSIVE VALIDATION")
print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("="*80)

results = []

for league_code in ALL_LEAGUES:
    conf = LEAGUE_CONFIGS.get(league_code)
    if not conf:
        continue
    
    comp_id = conf.get("competition_id")
    current_thresh = conf.get("threshold", 0.50)
    
    print(f"\n{'='*60}")
    print(f"  {league_code} (CompID: {comp_id}, DefaultThresh: {current_thresh})")
    print(f"{'='*60}")
    
    with db_manager.session() as session:
        repo = FeatureRepository(session, config.get('features', {}))
        
        try:
            X, y = repo.get_training_data(competition_id=comp_id, target_column='target_over_25')
            
            if len(X) < 50:
                print(f"  [SKIP] Insufficient data: {len(X)} samples")
                results.append({
                    'league': league_code,
                    'status': 'insufficient_data',
                    'samples': len(X)
                })
                continue
                
            print(f"  Data: {len(X)} samples, Target: {y.mean():.1%}")
            
            trainer = ModelTrainer(model_config)
            trainer.feature_names = list(X.columns)
            X_train, X_test, y_train, y_test = trainer.prepare_data(X, y)
            trainer.train_ensemble(X_train, y_train)
            
            y_prob = trainer.ensemble_proba(X_test)
            y_pred = trainer.ensemble_predict(X_test)
            
            # Test recommended threshold from improvement script
            optimal_thresholds = {
                "SA": 0.70, "PD": 0.35, "FL1": 0.40
            }
            test_thresh = optimal_thresholds.get(league_code, current_thresh)
            
            mask = y_prob >= test_thresh
            n_bets = mask.sum()
            
            if n_bets < 10:
                # Try to find better threshold
                test_thresh = 0.50
                mask = y_prob >= test_thresh
                n_bets = mask.sum()
            
            if n_bets < 10:
                print(f"  [WARN] Too few bets: {n_bets}")
                results.append({
                    'league': league_code,
                    'status': 'low_volume',
                    'bets': n_bets
                })
                continue
            
            preds = y_pred[mask]
            actuals = y_test.values[mask]
            probs = y_prob[mask]
            
            wins = (preds == actuals).sum()
            win_rate = wins / n_bets
            
            total_return = sum(odds_manager.get_over_25_odds(league_code, p) for p in probs)
            avg_odds = total_return / n_bets
            roi = ((win_rate * avg_odds - 1) * 100)
            
            print(f"\n  Results at threshold {test_thresh:.2f}:")
            print(f"    Bets: {n_bets}")
            print(f"    Win Rate: {win_rate*100:.1f}%")
            print(f"    Avg Odds: {avg_odds:.2f}")
            print(f"    ROI: {roi:+.1f}%")
            
            # Determine production readiness
            if roi >= 5 and n_bets >= 30:
                status = "production"
            elif roi >= 0 and n_bets >= 20:
                status = "testing"
            else:
                status = "needs_work"
            
            results.append({
                'league': league_code,
                'competition_id': comp_id,
                'threshold': test_thresh,
                'bets': n_bets,
                'win_rate': win_rate * 100,
                'avg_odds': avg_odds,
                'roi': roi,
                'status': status
            })
            
        except Exception as e:
            print(f"  [ERROR] {e}")
            results.append({
                'league': league_code,
                'error': str(e),
                'status': 'error'
            })

odds_manager.close()

# Final Summary
print("\n" + "="*80)
print("  FINAL LEAGUE STATUS")
print("="*80)

print(f"\n  {'League':<8} | {'CompID':<7} | {'Thresh':<7} | {'Bets':<6} | {'Win%':<7} | {'ROI':<8} | {'Status'}")
print(f"  {'-'*8}-+-{'-'*7}-+-{'-'*7}-+-{'-'*6}-+-{'-'*7}-+-{'-'*8}-+-{'-'*12}")

production = []
testing = []

for r in results:
    league = r.get('league', '???')
    status = r.get('status', 'unknown')
    
    if r.get('error'):
        status_str = "ERROR"
        print(f"  {league:<8} |          |        |        |         |          | {status_str}")
    elif status == 'insufficient_data':
        print(f"  {league:<8} |          |        |        |         |          | NO DATA")
    else:
        if status == "production":
            production.append(r)
            status_str = "[PROD]"
        elif status == "testing":
            testing.append(r)
            status_str = "[TEST]"
        else:
            status_str = "[WORK]"
        
        print(f"  {league:<8} | {r.get('competition_id', 0):<7} | {r.get('threshold', 0):<7.2f} | {r.get('bets', 0):<6} | {r.get('win_rate', 0):<6.1f}% | {r.get('roi', 0):+7.1f}% | {status_str}")

print(f"\n  Production Leagues: {len(production)}")
print(f"  Testing: {len(testing)}")

# Update configs
print("\n" + "="*80)
print("  UPDATED CONFIGURATION")
print("="*80)

for r in production:
    league = r['league']
    thresh = r['threshold']
    roi = r['roi']
    print(f"  {league}: threshold={thresh:.2f}, status=production # ROI: {roi:+.1f}%")

for r in testing:
    league = r['league']
    thresh = r['threshold']
    roi = r['roi']
    print(f"  {league}: threshold={thresh:.2f}, status=testing # ROI: {roi:+.1f}%")

print("\n[COMPLETE]")
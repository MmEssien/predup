"""
Comprehensive League Validation - Test all configured leagues
Find optimal thresholds and validate production readiness
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
feature_config = config.get('features', {})

db_manager = DatabaseManager.get_instance()
db_manager.initialize()

odds_manager = OddsManager(use_real_api=False)

print("="*80)
print("  COMPREHENSIVE LEAGUE VALIDATION")
print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("="*80)

results = []

# Test each configured league
for league_code, conf in LEAGUE_CONFIGS.items():
    if conf.get("status") == "paused":
        continue
    
    api_id = conf.get("api_id")
    comp_id = conf.get("competition_id")
    
    print(f"\n{'='*60}")
    print(f"  {league_code} (API:{api_id}, CompID:{comp_id})")
    print(f"{'='*60}")
    
    with db_manager.session() as session:
        repo = FeatureRepository(session, feature_config)
        
        try:
            X, y = repo.get_training_data(
                competition_id=comp_id, 
                target_column='target_over_25'
            )
            
            if len(X) < 50:
                print(f"  [SKIP] Insufficient data: {len(X)} samples")
                results.append({
                    'league': league_code,
                    'status': 'insufficient_data',
                    'samples': len(X)
                })
                continue
            
            print(f"  Data: {len(X)} samples")
            
            trainer = ModelTrainer(model_config)
            trainer.feature_names = list(X.columns)
            X_train, X_test, y_train, y_test = trainer.prepare_data(X, y)
            trainer.train_ensemble(X_train, y_train)
            
            y_prob = trainer.ensemble_proba(X_test)
            y_pred = trainer.ensemble_predict(X_test)
            
            # Test multiple thresholds
            print(f"\n  Threshold Analysis:")
            print(f"  Thresh | Bets | Win%  | AvgOdds | ROI(%)")
            print(f"  -------|------|-------|---------|--------")
            
            best_roi = -999
            best_thresh = 0.5
            
            for thresh in [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85]:
                mask = y_prob >= thresh
                n_bets = mask.sum()
                
                if n_bets < 10:
                    continue
                
                preds = y_pred[mask]
                actuals = y_test.values[mask]
                probs = y_prob[mask]
                
                wins = (preds == actuals).sum()
                win_rate = wins / n_bets
                
                # Calculate ROI with realistic odds
                total_return = 0
                for p in probs:
                    over_odds = odds_manager.get_over_25_odds(league_code, p)
                    total_return += over_odds
                
                avg_odds = total_return / n_bets
                roi = ((win_rate * avg_odds - 1) * 100)
                
                print(f"  {thresh:.2f}   | {n_bets:4d} | {win_rate*100:5.1f}% | {avg_odds:6.2f} | {roi:+6.1f}%")
                
                if roi > best_roi:
                    best_roi = roi
                    best_thresh = thresh
            
            print(f"\n  Best: threshold={best_thresh:.2f}, ROI={best_roi:+.1f}%")
            
            # Determine status
            if best_roi >= 5:
                status = "production_ready"
            elif best_roi >= 0:
                status = "testing"
            else:
                status = "needs_work"
            
            results.append({
                'league': league_code,
                'api_id': api_id,
                'comp_id': comp_id,
                'samples': len(X),
                'best_threshold': best_thresh,
                'best_roi': best_roi,
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

# Summary
print("\n" + "="*80)
print("  LEAGUE VALIDATION SUMMARY")
print("="*80)

print(f"\n  {'League':<8} | {'API':<5} | {'Samples':<8} | {'BestTh':<8} | {'ROI':<8} | {'Status'}")
print(f"  {'-'*8}-+-{'-'*5}-+-{'-'*8}-+-{'-'*8}-+-{'-'*8}-+-{'-'*12}")

production_ready = []
testing = []
needs_work = []

for r in results:
    if r.get('error'):
        print(f"  {r['league']:<8} |     |          |          |          | ERROR")
    else:
        status = r.get('status', 'unknown')
        roi = r.get('best_roi', 0)
        
        if status == 'production_ready':
            production_ready.append(r)
            status_str = "[PROD]"
        elif status == 'testing':
            testing.append(r)
            status_str = "[TEST]"
        else:
            needs_work.append(r)
            status_str = "[WORK]"
        
        print(f"  {r['league']:<8} | {r.get('api_id', 0):<5} | {r.get('samples', 0):<8} | {r.get('best_threshold', 0):<8.2f} | {roi:+7.1f}% | {status_str}")

print(f"\n  Production Ready: {len(production_ready)}")
print(f"  Testing: {len(testing)}")
print(f"  Needs Work: {len(needs_work)}")

# Update configs for production-ready leagues
print("\n" + "="*80)
print("  RECOMMENDED CONFIGURATION")
print("="*80)

print("\n  Production Leagues:")
for r in production_ready:
    print(f"    {r['league']}: threshold={r['best_threshold']:.2f}, ROI={r['best_roi']:+.1f}%")

print("\n  Testing Leagues:")
for r in testing:
    print(f"    {r['league']}: threshold={r['best_threshold']:.2f}, ROI={r['best_roi']:+.1f}%")

print("\n  Leagues Needing More Work:")
for r in needs_work:
    print(f"    {r['league']}: ROI={r.get('best_roi', 0):+.1f}%")

print("\n[COMPLETE]")
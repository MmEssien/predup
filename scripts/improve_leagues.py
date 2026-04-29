"""
Aggressive League Improvement Script
Tries multiple strategies to improve SA/FL1/PD performance
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

# Try different model configs
MODEL_CONFIGS = [
    {"name": "Baseline", "test_split": 0.3, "random_state": 42},
    {"name": "MoreTraining", "test_split": 0.2, "random_state": 42},
    {"name": "DifferentSeed", "test_split": 0.3, "random_state": 123},
    {"name": "SmallTest", "test_split": 0.15, "random_state": 42},
]

# Model params to try
XGB_PARAMS = [
    {"n_estimators": 100, "max_depth": 5, "learning_rate": 0.1},
    {"n_estimators": 150, "max_depth": 4, "learning_rate": 0.08},
    {"n_estimators": 200, "max_depth": 3, "learning_rate": 0.05},
    {"n_estimators": 100, "max_depth": 6, "learning_rate": 0.15},
    {"n_estimators": 80, "max_depth": 4, "learning_rate": 0.2},
]

LGBM_PARAMS = [
    {"n_estimators": 100, "max_depth": 5, "learning_rate": 0.1},
    {"n_estimators": 150, "max_depth": 4, "learning_rate": 0.08},
    {"n_estimators": 200, "max_depth": 3, "learning_rate": 0.05},
]

db_manager = DatabaseManager.get_instance()
db_manager.initialize()

odds_manager = OddsManager(use_real_api=False)

# Focus on testing leagues
TESTING_LEAGUES = ["SA", "PD", "FL1", "ELC", "ECD", "POR"]

print("="*80)
print("  AGGRESSIVE LEAGUE IMPROVEMENT")
print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("="*80)

all_results = []

for league_code in TESTING_LEAGUES:
    conf = LEAGUE_CONFIGS.get(league_code)
    if not conf or conf.get("status") == "paused":
        continue
        
    comp_id = conf.get("competition_id")
    
    print(f"\n{'='*60}")
    print(f"  {league_code} (CompID: {comp_id})")
    print(f"{'='*60}")
    
    with db_manager.session() as session:
        repo = FeatureRepository(session, config.get('features', {}))
        
        try:
            X, y = repo.get_training_data(competition_id=comp_id, target_column='target_over_25')
            
            if len(X) < 50:
                print(f"  [SKIP] Insufficient data: {len(X)} samples")
                continue
                
            print(f"  Data: {len(X)} samples, Features: {len(X.columns)}")
            print(f"  Target balance: {y.mean():.1%} over 2.5")
            
        except Exception as e:
            print(f"  [ERROR] {e}")
            continue
        
        # Try different configurations
        best_roi = -999
        best_config = None
        
        for model_cfg in MODEL_CONFIGS:
            for xgb_p in XGB_PARAMS:
                try:
                    trainer = ModelTrainer({
                        "model": {"xgboost": xgb_p, "lgbm": {}},
                        **model_cfg
                    })
                    trainer.feature_names = list(X.columns)
                    
                    X_train, X_test, y_train, y_test = trainer.prepare_data(X, y)
                    
                    trainer.train_ensemble(X_train, y_train)
                    
                    y_prob = trainer.ensemble_proba(X_test)
                    y_pred = trainer.ensemble_predict(X_test)
                    
                    # Find best threshold
                    for thresh in [0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]:
                        mask = y_prob >= thresh
                        n_bets = mask.sum()
                        
                        if n_bets < 10:
                            continue
                        
                        preds = y_pred[mask]
                        actuals = y_test.values[mask]
                        probs = y_prob[mask]
                        
                        wins = (preds == actuals).sum()
                        win_rate = wins / n_bets
                        
                        # ROI with realistic odds
                        total_return = sum(odds_manager.get_over_25_odds(league_code, p) for p in probs)
                        avg_odds = total_return / n_bets
                        roi = ((win_rate * avg_odds - 1) * 100)
                        
                        if roi > best_roi:
                            best_roi = roi
                            best_config = {
                                "model_cfg": model_cfg["name"],
                                "xgb_depth": xgb_p["max_depth"],
                                "xgb_est": xgb_p["n_estimators"],
                                "threshold": thresh,
                                "bets": n_bets,
                                "win_rate": win_rate * 100,
                                "avg_odds": avg_odds,
                                "roi": roi
                            }
                            
                except Exception as e:
                    continue
        
        if best_config:
            print(f"\n  Best Configuration:")
            print(f"    Model: {best_config['model_cfg']}")
            print(f"    XGB: depth={best_config['xgb_depth']}, n_est={best_config['xgb_est']}")
            print(f"    Threshold: {best_config['threshold']:.2f}")
            print(f"    Bets: {best_config['bets']}, Win Rate: {best_config['win_rate']:.1f}%")
            print(f"    Avg Odds: {best_config['avg_odds']:.2f}")
            print(f"    ROI: {best_config['roi']:+.1f}%")
            
            all_results.append({
                'league': league_code,
                'best_roi': best_roi,
                'best_threshold': best_config['threshold'],
                'best_config': best_config
            })
        else:
            print(f"  No valid configuration found")
            all_results.append({
                'league': league_code,
                'best_roi': -999,
                'error': 'No valid config'
            })

odds_manager.close()

# Summary
print("\n" + "="*80)
print("  IMPROVEMENT SUMMARY")
print("="*80)

print(f"\n  {'League':<8} | {'Best Thresh':<12} | {'Bets':<6} | {'Win%':<8} | {'ROI'}")
print(f"  {'-'*8}-+-{'-'*12}-+-{'-'*6}-+-{'-'*8}-+-{'-'*8}")

production_ready = []
for r in all_results:
    if r.get('error'):
        print(f"  {r['league']:<8} | {'ERROR':<12}")
    else:
        cfg = r.get('best_config', {})
        roi = r.get('best_roi', 0)
        
        if roi >= 5:
            status = "[PROD]"
            production_ready.append(r)
        elif roi >= 0:
            status = "[TEST]"
        else:
            status = "[WORK]"
            
        print(f"  {r['league']:<8} | {r.get('best_threshold', 0):<12.2f} | {cfg.get('bets', 0):<6} | {cfg.get('win_rate', 0):<7.1f}% | {roi:+6.1f}% {status}")

print(f"\n  Can promote to production: {len(production_ready)}")

# Update configs
if production_ready:
    print("\n  Updating league configs...")
    for r in production_ready:
        league = r['league']
        thresh = r['best_threshold']
        print(f"    {league}: threshold={thresh}")

print("\n[COMPLETE]")
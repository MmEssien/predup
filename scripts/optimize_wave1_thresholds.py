"""
Wave 1 - Threshold Optimization
Find optimal thresholds for each new league
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import numpy as np
import pandas as pd

from src.data.connection import DatabaseManager
from src.features.repository import FeatureRepository
from src.models.trainer import ModelTrainer
from src.models.evaluator import Backtester
from src.utils.helpers import load_config
import warnings
warnings.filterwarnings('ignore')

config = load_config()
model_config = config.get('model', {})
feature_config = config.get('features', {})

db_manager = DatabaseManager.get_instance()
db_manager.initialize()

WAVE1_LEAGUES = {
    "sa": {"comp_id": 8},
    "pd": {"comp_id": 12},  
    "fl1": {"comp_id": 6},
}

print("="*70)
print("  WAVE 1 - THRESHOLD OPTIMIZATION")
print("="*70)

results = []

for league_code, config_dict in WAVE1_LEAGUES.items():
    comp_id = config_dict["comp_id"]
    
    print(f"\n--- {league_code.upper()} Threshold Analysis ---")
    
    with db_manager.session() as session:
        repo = FeatureRepository(session, feature_config)
        X, y = repo.get_training_data(competition_id=comp_id, target_column='target_over_25')
        
        trainer = ModelTrainer(model_config)
        trainer.feature_names = list(X.columns)
        X_train, X_test, y_train, y_test = trainer.prepare_data(X, y)
        trainer.train_ensemble(X_train, y_train)
        
        y_prob = trainer.ensemble_proba(X_test)
        y_pred = trainer.ensemble_predict(X_test)
        
        backtester = Backtester(initial_bankroll=1000.0)
        
        best_roi = -100
        best_threshold = 0.5
        
        print(f"  Threshold | Bets | WinRate | ROI")
        print(f"  ----------|------|---------|------")
        
        for threshold in [0.45, 0.50, 0.55, 0.58, 0.60, 0.62, 0.65, 0.68, 0.70, 0.72, 0.75]:
            results_th = backtester.run_backtest(
                predictions=y_pred,
                probabilities=y_prob,
                actuals=y_test.values,
                stake=1.0,
                confidence_threshold=threshold
            )
            
            if results_th['total_bets'] >= 10:  # Minimum bet requirement
                print(f"  {threshold:.2f}     | {results_th['total_bets']:3d}  | {results_th['win_rate']*100:5.1f}% | {results_th['roi']:+5.1f}%")
                
                if results_th['roi'] > best_roi:
                    best_roi = results_th['roi']
                    best_threshold = threshold
        
        print(f"\n  Best for {league_code.upper()}: threshold={best_threshold:.2f} with ROI={best_roi:+.2f}%")
        
        results.append({
            'League': league_code.upper(),
            'Best_Threshold': best_threshold,
            'Best_ROI': best_roi
        })

print("\n" + "="*70)
print("  OPTIMAL THRESHOLDS FOUND")
print("="*70)

for r in results:
    print(f"  {r['League']}: {r['Best_Threshold']} -> {r['Best_ROI']:+.2f}%")

print("\n[COMPLETE]")
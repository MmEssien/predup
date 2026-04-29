"""
Validation Script - Test Optimized Thresholds and Calibration

Validates:
1. League threshold updates (BL1: 0.70, PL: 0.70)
2. Calibration improvements
3. Overall performance

Usage:
    python scripts/validate_optimized.py
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
from src.models.calibrator import LeagueCalibrator
from src.decisions.engine import LEAGUE_CONFIGS, ENABLED_LEAGUES
from src.utils.helpers import load_config
import warnings
warnings.filterwarnings('ignore')

config = load_config()
model_config = config.get('model', {})
feature_config = config.get('features', {})

db_manager = DatabaseManager.get_instance()
db_manager.initialize()

# New thresholds from analysis
print("="*60)
print("  VALIDATION - OPTIMIZED SYSTEM")
print("="*60)

print("\n[1] League Thresholds (Updated):")
for league, conf in LEAGUE_CONFIGS.items():
    print(f"    {league}: {conf['threshold']}")

results_by_league = []
total_profit = 0
total_bets = 0

for league_name in ENABLED_LEAGUES:
    comp_id = LEAGUE_CONFIGS[league_name]['competition_id']
    threshold = LEAGUE_CONFIGS[league_name]['threshold']
    
    print(f"\n[2] Processing {league_name}...")
    
    with db_manager.session() as session:
        repo = FeatureRepository(session, feature_config)
        X, y = repo.get_training_data(
            competition_id=comp_id, 
            target_column='target_over_25'
        )
        
        # Train/test split
        trainer = ModelTrainer(model_config)
        trainer.feature_names = list(X.columns)
        X_train, X_test, y_train, y_test = trainer.prepare_data(X, y)
        trainer.train_ensemble(X_train, y_train)
        
        # Raw predictions
        y_prob_raw = trainer.ensemble_proba(X_test)
        y_pred_raw = trainer.ensemble_predict(X_test)
        
        # Fit calibration
        print(f"    Training calibrator...")
        calibrator = LeagueCalibrator()
        calibrator.fit_league(league_name, y_train.values, trainer.ensemble_proba(X_train))
        
        # Calibrated predictions
        y_prob_cal = calibrator.transform(y_prob_raw, league_name)
        
        # Now test with HIGH threshold
        backtester = Backtester(initial_bankroll=1000.0 / len(ENABLED_LEAGUES))
        
        raw_results = backtester.run_backtest(
            predictions=y_pred_raw,
            probabilities=y_prob_raw,
            actuals=y_test.values,
            stake=1.0,
            confidence_threshold=threshold
        )
        
        # Calibrated results  
        backtester2 = Backtester(initial_bankroll=1000.0 / len(ENABLED_LEAGUES))
        
        # Use threshold on calibrated probabilities
        y_pred_cal = (y_prob_cal >= threshold).astype(int)
        
        cal_results = backtester2.run_backtest(
            predictions=y_pred_cal,
            probabilities=y_prob_cal,
            actuals=y_test.values,
            stake=1.0,
            confidence_threshold=threshold
        )
        
        print(f"\n    Raw Predictions (threshold={threshold}):")
        print(f"      Bets: {raw_results['total_bets']}, Win Rate: {raw_results['win_rate']*100:.1f}%, ROI: {raw_results['roi']:+.2f}%")
        
        print(f"\n    Calibrated Predictions:")
        print(f"      Bets: {cal_results['total_bets']}, Win Rate: {cal_results['win_rate']*100:.1f}%, ROI: {cal_results['roi']:+.2f}%")
        
        results_by_league.append({
            'League': league_name,
            'Threshold': threshold,
            'Raw_Bets': raw_results['total_bets'],
            'Raw_WinRate': f"{raw_results['win_rate']*100:.1f}%",
            'Raw_ROI': f"{raw_results['roi']:+.2f}%",
            'Cal_Bets': cal_results['total_bets'],
            'Cal_WinRate': f"{cal_results['win_rate']*100:.1f}%",
            'Cal_ROI': f"{cal_results['roi']:+.2f}%"
        })
        
        total_bets += cal_results['total_bets']
        total_profit += cal_results['total_profit']

print("\n" + "="*60)
print("  SUMMARY")
print("="*60)

import pandas as pd
df = pd.DataFrame(results_by_league)
print("\nResults by League:")
print("-"*60)
pd.set_option('display.width', 120)
print(df.to_string(index=False))

print(f"\nTotal Bets: {total_bets}")
print(f"Total Profit: ${total_profit:+.2f}")
print(f"Overall ROI: {(total_profit/1000)*100:+.2f}%")

print("\n[COMPLETE]")
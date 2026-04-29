"""
Deep Hardening - Odds Intelligence + Confidence Band Analysis
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
from src.decisions.engine import LEAGUE_CONFIGS
from src.utils.helpers import load_config
import warnings
warnings.filterwarnings('ignore')

config = load_config()
model_config = config.get('model', {})
feature_config = config.get('features', {})

db_manager = DatabaseManager.get_instance()
db_manager.initialize()

ACTIVE_LEAGUES = ["BL1", "PL", "SA", "PD", "FL1"]

print("="*70)
print("  ODDS INTELLIGENCE + CONFIDENCE BAND ANALYSIS")
print("="*70)

# Simulate odds-based analysis (since we don't have actual odds in DB)
# We'll use implied probability analysis

for league_code in ACTIVE_LEAGUES:
    league_conf = LEAGUE_CONFIGS.get(league_code)
    if not league_conf:
        continue
        
    comp_id = league_conf["competition_id"]
    threshold = league_conf["threshold"]
    
    print(f"\n{'='*60}")
    print(f"  {league_code} (threshold={threshold})")
    print(f"{'='*60}")
    
    with db_manager.session() as session:
        repo = FeatureRepository(session, feature_config)
        
        try:
            X, y = repo.get_training_data(competition_id=comp_id, target_column='target_over_25')
            
            trainer = ModelTrainer(model_config)
            trainer.feature_names = list(X.columns)
            X_train, X_test, y_train, y_test = trainer.prepare_data(X, y)
            trainer.train_ensemble(X_train, y_train)
            
            y_prob = trainer.ensemble_proba(X_test)
            y_pred = trainer.ensemble_predict(X_test)
            
            # Confidence band analysis
            print(f"\n  Confidence Band Analysis:")
            print(f"  Band      | Bets | WinRate | ROI  | Expected vs Actual")
            print(f"  ----------|------|---------|------|--------------------")
            
            bands = [
                (0.40, 0.50, "Low"),
                (0.50, 0.60, "Med"),
                (0.60, 0.70, "High"),
                (0.70, 1.00, "VHigh"),
            ]
            
            for low, high, name in bands:
                mask = (y_prob >= low) & (y_prob < high)
                if mask.sum() > 0:
                    band_preds = y_pred[mask]
                    band_actual = y_test.values[mask]
                    band_prob = y_prob[mask]
                    
                    wins = (band_preds == band_actual).sum()
                    total = len(band_preds)
                    win_rate = wins / total if total > 0 else 0
                    
                    # ROI calculation (assume 1.90 odds)
                    roi = (wins * 0.9 - (total - wins)) / total * 100 if total > 0 else 0
                    
                    # Expected vs Actual
                    avg_pred_prob = band_prob.mean()
                    actual_rate = win_rate
                    diff = actual_rate - avg_pred_prob
                    
                    print(f"  {name:<8} | {total:4d} | {win_rate*100:5.1f}% | {roi:+5.1f}% | Pred={avg_pred_prob:.0%}, Actual={actual_rate:.0%}, Diff={diff:+.0%}")
            
            # Simulated odds analysis
            print(f"\n  Odds Intelligence (Simulated at 1.90):")
            
            # Calculate edge for different probability thresholds
            print(f"  Threshold | Model% | Implied% | Edge  | EV/Bet")
            print(f"  ----------|---------|-----------|-------|--------")
            
            for thresh in [0.50, 0.55, 0.60, 0.65, 0.70, 0.75]:
                mask = y_prob >= thresh
                if mask.sum() > 5:
                    wins = (y_pred[mask] == y_test.values[mask]).sum()
                    total = mask.sum()
                    win_rate = wins / total
                    
                    implied = 1 / 1.90  # 52.6%
                    edge = win_rate - implied
                    ev = edge * 1.90  # approximate EV per unit stake
                    
                    print(f"  {thresh:.2f}     | {win_rate*100:5.1f}% |    {implied*100:.1f}%  | {edge*100:+4.1f}% | {ev:+.3f}")
            
            # Volume analysis
            print(f"\n  Volume Analysis:")
            for thresh in [0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]:
                mask = y_prob >= thresh
                if mask.sum() > 0:
                    print(f"    >= {thresh:.2f}: {mask.sum()} bets")
                    
        except Exception as e:
            print(f"  Error: {e}")

print("\n[COMPLETE]")
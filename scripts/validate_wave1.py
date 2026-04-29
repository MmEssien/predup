"""
Wave 1 Validation - SA, PD, FL1
Run validation on new leagues with tier-appropriate thresholds

SA: 0.68
PD: 0.70
FL1: 0.72
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
from src.decisions.engine import IntelligenceEngine, LEAGUE_CONFIGS
from src.utils.helpers import load_config
import warnings
warnings.filterwarnings('ignore')

config = load_config()
model_config = config.get('model', {})
feature_config = config.get('features', {})

db_manager = DatabaseManager.get_instance()
db_manager.initialize()

# Wave 1 leagues configuration
WAVE1_LEAGUES = {
    "sa": {"comp_id": 8, "threshold": 0.68, "tier": 1},
    "pd": {"comp_id": 12, "threshold": 0.70, "tier": 1},  
    "fl1": {"comp_id": 6, "threshold": 0.72, "tier": 1},
}

print("="*70)
print("  WAVE 1 VALIDATION - SA, PD, FL1")
print("="*70)

results = []

for league_code, config_dict in WAVE1_LEAGUES.items():
    comp_id = config_dict["comp_id"]
    threshold = config_dict["threshold"]
    tier = config_dict["tier"]
    
    print(f"\n{'='*60}")
    print(f"Processing {league_code.upper()} (Tier {tier}, threshold={threshold})")
    print(f"{'='*60}")
    
    with db_manager.session() as session:
        repo = FeatureRepository(session, feature_config)
        
        try:
            X, y = repo.get_training_data(
                competition_id=comp_id,
                target_column='target_over_25'
            )
            
            if len(X) < 100:
                print(f"  SKIP: Only {len(X)} samples")
                continue
                
            print(f"  Data: {len(X)} training samples")
            
            # Train model
            trainer = ModelTrainer(model_config)
            trainer.feature_names = list(X.columns)
            X_train, X_test, y_train, y_test = trainer.prepare_data(X, y)
            trainer.train_ensemble(X_train, y_train)
            
            # Get predictions
            y_prob_raw = trainer.ensemble_proba(X_test)
            y_pred_raw = trainer.ensemble_predict(X_test)
            
            # Fit calibration
            calibrator = LeagueCalibrator()
            calibrator.fit_league(league_code.upper(), y_train.values, trainer.ensemble_proba(X_train))
            
            # Calibrate
            y_prob_cal = calibrator.transform(y_prob_raw, league_code.upper())
            
            # Run backtest with threshold
            backtester = Backtester(initial_bankroll=1000.0)
            
            # Using calibrated probabilities with threshold
            results_raw = backtester.run_backtest(
                predictions=y_pred_raw,
                probabilities=y_prob_raw,  # Use raw for now
                actuals=y_test.values,
                stake=1.0,
                confidence_threshold=threshold
            )
            
            results_cal = backtester.run_backtest(
                predictions=(y_prob_cal >= threshold).astype(int),
                probabilities=y_prob_cal,
                actuals=y_test.values,
                stake=1.0,
                confidence_threshold=threshold
            )
            
            print(f"\n  Raw Predictions (threshold={threshold}):")
            print(f"    Bets: {results_raw['total_bets']}")
            print(f"    Win Rate: {results_raw['win_rate']*100:.1f}%")
            print(f"    ROI: {results_raw['roi']:+.2f}%")
            
            print(f"\n  Calibrated (if used):")
            print(f"    Bets: {results_cal['total_bets']}")
            print(f"    Win Rate: {results_cal['win_rate']*100:.1f}%")  
            print(f"    ROI: {results_cal['roi']:+.2f}%")
            
            results.append({
                'League': league_code.upper(),
                'Tier': tier,
                'Threshold': threshold,
                'Bets': results_raw['total_bets'],
                'WinRate': f"{results_raw['win_rate']*100:.1f}%",
                'Raw_ROI': f"{results_raw['roi']:+.2f}%",
                'Cal_ROI': f"{results_cal['roi']:+.2f}%",
                'Profit': f"${results_raw['total_profit']:+.2f}"
            })
            
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()

# Summary
print("\n" + "="*70)
print("  WAVE 1 SUMMARY")
print("="*70)

df = pd.DataFrame(results)
if len(df) > 0:
    print("\n" + df.to_string(index=False))
    
    # Compare to baseline
    print("\n  Comparison to Core Leagues:")
    print("  --------------------------")
    print("  League   Threshold   Bets   WinRate    ROI")
    print("  ----------------------------------------")
    print("  BL1      0.70       132    64.4%    +7.60%   (baseline)")
    print("  PL       0.70       114    58.8%    +4.00%   (baseline)")
    
    for _, row in df.iterrows():
        print(f"  {row['League']:<8} {row['Threshold']}       {row['Bets']:<5} {row['WinRate']:<8} {row['Raw_ROI']}")
    
    # Recommendations
    print("\n  Recommendations:")
    print("  ---------------")
    for _, row in df.iterrows():
        roi_val = float(row['Raw_ROI'].replace('%','').replace('+',''))
        if roi_val >= 3:
            print(f"  - {row['League']}: STRONG ({roi_val:+.0f}%) - Production ready")
        elif roi_val >= 0:
            print(f"  - {row['League']}: ACCEPTABLE ({roi_val:+.0f}%) - Use with standard thresholds")
        else:
            print(f"  - {row['League']}: WEAK ({roi_val:+.0f}%) - Consider raising threshold or tier down")
else:
    print("No results to display")

print("\n[COMPLETE]")
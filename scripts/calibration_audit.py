"""
Deep Hardening - Calibration Audit
Run comprehensive calibration analysis across all 5 active leagues
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
print("  CALIBRATION AUDIT - ALL 5 ACTIVE LEAGUES")
print("="*70)

all_results = []

for league_code in ACTIVE_LEAGUES:
    league_conf = LEAGUE_CONFIGS.get(league_code)
    if not league_conf:
        continue
        
    comp_id = league_conf["competition_id"]
    threshold = league_conf["threshold"]
    
    print(f"\n{'='*60}")
    print(f"  {league_code} Analysis (threshold={threshold}, tier={league_conf['tier']})")
    print(f"{'='*60}")
    
    with db_manager.session() as session:
        repo = FeatureRepository(session, feature_config)
        
        try:
            X, y = repo.get_training_data(competition_id=comp_id, target_column='target_over_25')
            
            if len(X) < 100:
                print(f"  SKIP: Only {len(X)} samples")
                continue
            
            # Train model
            trainer = ModelTrainer(model_config)
            trainer.feature_names = list(X.columns)
            X_train, X_test, y_train, y_test = trainer.prepare_data(X, y)
            trainer.train_ensemble(X_train, y_train)
            
            # Get predictions
            y_prob = trainer.ensemble_proba(X_test)
            y_prob_raw = y_prob.copy()
            
# Get calibration and apply it
            calibrator = LeagueCalibrator()
            calibrator.fit_league(league_code, y_train.values, trainer.ensemble_proba(X_train))
            y_prob_cal = calibrator.transform(y_prob, league_code)
            
            # Calibration analysis
            print(f"\n  Calibration Metrics:")
            if calibrator.calibrators and league_code in calibrator.calibrators:
                metrics = calibrator.calibrators[league_code].get_calibration_metrics()
                print(f"    ECE (Expected Calibration Error): {metrics.get('ece',0):.4f}")
                print(f"    MCE (Maximum Calibration Error): {metrics.get('mce', 0):.4f}")
            
            # Probability distribution analysis
            print(f"\n  Probability Distribution:")
            print(f"    Raw - Mean: {y_prob_raw.mean():.3f}, Std: {y_prob_raw.std():.3f}")
            print(f"    Cal - Mean: {y_prob_cal.mean():.3f}, Std: {y_prob_cal.std():.3f}")
            
            # Calibration curve
            print(f"\n  Calibration Curve:")
            if calibrator.calibrators and league_code in calibrator.calibrators:
                curve = calibrator.calibrators[league_code].calibration_curve
                for bin_data in curve[:5]:
                    print(f"    {bin_data['bin_start']:.0%}-{bin_data['bin_end']:.0%}: "
                          f"Pred={bin_data['mean_predicted']:.0%}, "
                          f"Actual={bin_data['actual_positive_rate']:.0%}, "
                          f"Calibrated={bin_data['calibrated_prob']:.0%}, "
                          f"N={bin_data['n_samples']}")
            
            # Backtest with raw vs calibrated
            backtester_raw = Backtester(initial_bankroll=1000.0)
            backtester_cal = Backtester(initial_bankroll=1000.0)
            
            y_pred_raw = (y_prob_raw >= threshold).astype(int)
            y_pred_cal = (y_prob_cal >= threshold).astype(int)
            
            res_raw = backtester_raw.run_backtest(y_pred_raw, y_prob_raw, y_test.values, stake=1.0, confidence_threshold=threshold)
            res_cal = backtester_cal.run_backtest(y_pred_cal, y_prob_cal, y_test.values, stake=1.0, confidence_threshold=threshold)
            
            print(f"\n  Performance:")
            print(f"    Raw  - Bets: {res_raw['total_bets']}, WinRate: {res_raw['win_rate']*100:.1f}%, ROI: {res_raw['roi']:+.2f}%")
            print(f"    Cal  - Bets: {res_cal['total_bets']}, WinRate: {res_cal['win_rate']*100:.1f}%, ROI: {res_cal['roi']:+.2f}%")
            
            # Store results
            all_results.append({
                'League': league_code,
                'Threshold': threshold,
                'ECE': metrics.get('ece', 0) if metrics else 0,
                'MCE': metrics.get('mce', 0) if metrics else 0,
                'Raw_Bets': res_raw['total_bets'],
                'Raw_ROI': res_raw['roi'],
                'Cal_Bets': res_cal['total_bets'],
                'Cal_ROI': res_cal['roi'],
                'Raw_Mean_Prob': y_prob_raw.mean(),
                'Cal_Mean_Prob': y_prob_cal.mean()
            })
            
        except Exception as e:
            print(f"  ERROR: {e}")

# Summary
print("\n" + "="*70)
print("  CALIBRATION AUDIT SUMMARY")
print("="*70)

df = pd.DataFrame(all_results)
if len(df) > 0:
    print("\n  " + "League    | Thresh |  ECE  |  MCE  | RawBets | RawROI  | CalBets | CalROI")
    print("  " + "-"*75)
    for _, r in df.iterrows():
        print("  %-8s | %.2f   | %.3f | %.3f | %6d  | %+6.2f | %7d | %+6.2f" % (
            r['League'], r['Threshold'], r['ECE'], r['MCE'],
            r['Raw_Bets'], r['Raw_ROI'], r['Cal_Bets'], r['Cal_ROI']
        ))
    
    print("\n  Interpretation:")
    print("  - ECE < 0.05 = Well calibrated")
    print("  - ECE 0.05-0.10 = Acceptable")
    print("  - ECE > 0.10 = Needs improvement")

# Red flag analysis
print("\n  RED FLAG ANALYSIS:")
for _, r in df.iterrows():
    flags = []
    if r['ECE'] > 0.10:
        flags.append("HIGH ECE")
    if r['Raw_Bets'] < 20:
        flags.append("LOW VOLUME")
    if r['Raw_ROI'] < 0:
        flags.append("NEGATIVE ROI")
    if r['Cal_Mean_Prob'] < r['Raw_Mean_Prob'] * 0.8:
        flags.append("COMPRESSION")
    
    if flags:
        print(f"  {r['League']}: {', '.join(flags)}")
    else:
        print(f"  {r['League']}: OK")

print("\n[COMPLETE]")
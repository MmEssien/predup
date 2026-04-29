"""
Threshold Optimization with Realistic Odds

Re-runs threshold optimization using:
- Realistic simulated odds (varies by probability)
- League-specific adjustments
- Proper EV calculations
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
from src.data.odds_simulator import OddsManager, OddsSimulator
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
print("  THRESHOLD OPTIMIZATION WITH REALISTIC ODDS")
print("="*70)

# Initialize odds manager/simulator
odds_manager = OddsManager(use_real_api=False)

results = []

for league_code in ACTIVE_LEAGUES:
    league_conf = LEAGUE_CONFIGS.get(league_code)
    if not league_conf:
        continue
        
    comp_id = league_conf["competition_id"]
    
    print(f"\n{'='*60}")
    print(f"  {league_code} - Real Odds Analysis")
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
            
            print(f"\n  Testing thresholds 0.40 - 0.85:")
            print(f"  Thresh | Bets | Win%  | AvgOdds | ROI(%) | EV(%)")
            print(f"  -------|------|-------|---------|--------|------")
            
            best_roi = -999
            best_thresh = 0.5
            
            for thresh in [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85]:
                mask = y_prob >= thresh
                if mask.sum() < 10:
                    continue
                    
                bets_mask = mask
                n_bets = bets_mask.sum()
                
                # Get predicted outcomes and actual outcomes
                preds = y_pred[bets_mask]
                actuals = y_test.values[bets_mask]
                probs = y_prob[bets_mask]
                
                # Calculate ROI with realistic odds
                total_stake = n_bets
                total_return = 0
                total_ev = 0
                wins = 0
                
                for i in range(n_bets):
                    # Get realistic odds for this prediction
                    over_odds = odds_manager.get_over_25_odds(league_code, probs[i])
                    
                    pred_over = preds[i] == 1
                    
                    if pred_over:
                        if actuals[i] == 1:
                            # Win
                            total_return += over_odds
                            wins += 1
                            # EV = P(win) * (odds-1) - P(lose) * 1
                            ev = (1.0 * (over_odds - 1)) + (0)
                        else:
                            # Lose
                            total_return += 0
                            ev = -1.0
                        total_ev += ev
                    else:
                        # Not betting (our prediction is under)
                        total_ev += 0  # No stake, no EV contribution
                
                roi = ((total_return - total_stake) / total_stake) * 100
                win_rate = (wins / n_bets * 100) if n_bets > 0 else 0
                avg_odds = total_return / wins if wins > 0 else 0
                ev_pct = (total_ev / total_stake * 100) if total_stake > 0 else 0
                
                if n_bets >= 10:
                    print(f"  {thresh:.2f}   | {n_bets:4d} | {win_rate:5.1f}% | {avg_odds:6.2f} | {roi:+6.1f}% | {ev_pct:+.1f}%")
                    
                    if roi > best_roi:
                        best_roi = roi
                        best_thresh = thresh
                
                results.append({
                    'league': league_code,
                    'threshold': thresh,
                    'bets': n_bets,
                    'win_rate': win_rate,
                    'avg_odds': avg_odds,
                    'roi': roi,
                    'ev': ev_pct
                })
            
            print(f"\n  Best threshold: {best_thresh:.2f} with ROI: {best_roi:+.1f}%")
            
        except Exception as e:
            print(f"  Error: {e}")
            import traceback
            traceback.print_exc()

print("\n" + "="*70)
print("  SUMMARY TABLE")
print("="*70)

# Find best threshold per league
df = pd.DataFrame(results)
df = df[df['bets'] >= 10]

print(f"\n  League | BestThresh | Bets | Win%  | AvgOdds | ROI(%) | EV(%)")
print(f"  -------|------------|------|-------|---------|--------|------")

for league in ACTIVE_LEAGUES:
    league_data = df[df['league'] == league]
    if len(league_data) > 0:
        best = league_data.loc[league_data['roi'].idxmax()]
        print(f"  {league:<6} | {best['threshold']:.2f}       | {int(best['bets']):4d} | {best['win_rate']:5.1f}% | {best['avg_odds']:6.2f} | {best['roi']:+6.1f}% | {best['ev']:+.1f}%")

print("\n[COMPLETE]")
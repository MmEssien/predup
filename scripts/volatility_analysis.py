"""
Deep Hardening - Volatility and Drawdown Analysis
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
print("  VOLATILITY AND DRAWDOWN ANALYSIS")
print("="*70)

for league_code in ACTIVE_LEAGUES:
    league_conf = LEAGUE_CONFIGS.get(league_code)
    if not league_conf:
        continue
        
    comp_id = league_conf["competition_id"]
    threshold = league_conf["threshold"]
    
    print(f"\n{'='*60}")
    print(f"  {league_code} Volatility Analysis")
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
            
            # Run backtest with full history
            backtester = Backtester(initial_bankroll=1000.0)
            
            # Simulate sequential betting
            bets = []
            bankroll = 1000.0
            
            for i in range(len(y_prob)):
                if y_prob[i] >= threshold:
                    pred = y_pred[i]
                    actual = y_test.values[i]
                    odds = 1.90
                    
                    # Bet
                    if pred == 1:
                        if actual == 1:
                            profit = 0.9  # won
                        else:
                            profit = -1.0  # lost
                        bankroll += profit
                    else:
                        profit = 0
                    
                    bets.append({
                        'i': i,
                        'prob': y_prob[i],
                        'prediction': pred,
                        'actual': actual,
                        'profit': profit,
                        'bankroll': bankroll
                    })
            
            # Calculate metrics
            df = pd.DataFrame(bets)
            
            # Running max
            df['peak'] = df['bankroll'].cummax()
            df['drawdown'] = (df['peak'] - df['bankroll']) / df['peak']
            
            max_drawdown = df['drawdown'].max() * 100
            
            # Win/Loss streaks
            df['outcome'] = df['profit'].apply(lambda x: 'W' if x > 0 else 'L' if x < 0 else 'P')
            
            # Calculate streaks
            current_streak = 0
            max_win_streak = 0
            max_loss_streak = 0
            
            for _, row in df.iterrows():
                if row['outcome'] == 'W':
                    current_streak += 1
                    max_win_streak = max(max_win_streak, current_streak)
                elif row['outcome'] == 'L':
                    current_streak = -1
                    max_loss_streak = max(max_loss_streak, 1)
                else:
                    current_streak = 0
            
            # Count wins/losses
            wins = (df['profit'] > 0).sum()
            losses = (df['profit'] < 0).sum()
            total = wins + losses
            
            # Volatility metrics
            profit_std = df['profit'].std()
            profit_mean = df['profit'].mean()
            sharpe_approx = (profit_mean / profit_std * np.sqrt(252)) if profit_std > 0 else 0
            
            print(f"\n  Volatility Metrics:")
            print(f"    Total Bets: {total}")
            print(f"    Win Rate: {wins/total*100:.1f}%")
            print(f"    Max Drawdown: {max_drawdown:.1f}%")
            print(f"    Profit Std Dev: {profit_std:.3f}")
            print(f"    Sharpe-like Ratio: {sharpe_approx:.2f}")
            
            print(f"\n  Streak Analysis:")
            print(f"    Max Win Streak: {max_win_streak}")
            print(f"    Max Loss Streak: {max_loss_streak}")
            
            # Risk rating
            risk_score = 0
            if max_drawdown > 20:
                risk_score += 2
            elif max_drawdown > 10:
                risk_score += 1
            
            if max_loss_streak > 5:
                risk_score += 2
            elif max_loss_streak > 3:
                risk_score += 1
            
            risk_level = "LOW" if risk_score == 0 else "MEDIUM" if risk_score <= 2 else "HIGH"
            
            print(f"\n  Risk Rating: {risk_level} (score: {risk_score})")
            
            # ROI by segments
            n = len(df)
            segment1 = df.iloc[:n//3]
            segment2 = df.iloc[n//3:2*n//3]
            segment3 = df.iloc[2*n//3:]
            
            print(f"\n  Performance by Time Segment:")
            print(f"    Early (1/3): {segment1['profit'].sum():+.1f}")
            print(f"    Mid (1/3):   {segment2['profit'].sum():+.1f}")
            print(f"    Late (1/3):  {segment3['profit'].sum():+.1f}")
            
        except Exception as e:
            print(f"  Error: {e}")

print("\n[COMPLETE]")
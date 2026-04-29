"""
Full Intelligence Engine Backtest

Tests the complete pipeline:
1. Bayesian probability updates
2. Market fusion
3. Regime detection
4. Edge filtering
5. Kelly stake sizing

Usage:
    python scripts/backtest_intelligence_engine.py
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
from src.models.calibrator import LeagueCalibrator
from src.decisions.engine import DecisionEngine, IntelligenceEngine
from src.decisions.engine import LEAGUE_CONFIGS, ENABLED_LEAGUES
from src.utils.helpers import load_config
import warnings
warnings.filterwarnings('ignore')

config = load_config()
model_config = config.get('model', {})
feature_config = config.get('features', {})

db_manager = DatabaseManager.get_instance()
db_manager.initialize()

print("="*60)
print("  INTELLIGENCE ENGINE FULL BACKTEST")
print("="*60)

# Simulate betting with different approaches
LEAGUE_THRESHOLD = 0.70

results = []

for league_name in ENABLED_LEAGUES:
    comp_id = LEAGUE_CONFIGS[league_name]['competition_id']
    
    print(f"\n[Processing {league_name}]")
    
    with db_manager.session() as session:
        repo = FeatureRepository(session, feature_config)
        X, y = repo.get_training_data(
            competition_id=comp_id, 
            target_column='target_over_25'
        )
        
        trainer = ModelTrainer(model_config)
        trainer.feature_names = list(X.columns)
        X_train, X_test, y_train, y_test = trainer.prepare_data(X, y)
        trainer.train_ensemble(X_train, y_train)
        
        # Fit calibrator
        calibrator = LeagueCalibrator()
        calibrator.fit_league(league_name, y_train.values, trainer.ensemble_proba(X_train))
        
        # Get raw probabilities
        y_prob_raw = trainer.ensemble_proba(X_test)
        
        # Apply calibration
        y_prob_cal = calibrator.transform(y_prob_raw, league_name)
        
        # Get predictions for each fixture
        from src.data.database import Fixture
        fixtures = session.query(Fixture).filter(
            Fixture.competition_id == comp_id,
            Fixture.status == 'FINISHED',
            Fixture.home_score.isnot(None)
        ).all()
        
        print(f"    {len(fixtures)} fixtures, {len(y_prob_cal)} predictions")
        
        # Now process with FULL intelligent pipeline
        intell = IntelligenceEngine(league_code=league_name)
        
        accepted_bets = []
        rejected_bets = []
        
        # Mock odds (would come from OddsData in production)
        mock_odds = 1.90  # Average over 2.5 odds
        
        for i, (fixture, prob) in enumerate(zip(fixtures, y_prob_cal)):
            # Use probability as model prediction
            model_prob = prob
            
            # Mock model predictions dict
            model_preds = {
                "xgboost": model_prob * 0.98,
                "lightgbm": model_prob * 1.02,
                "logreg": model_prob * 0.95
            }
            
            # Create fixture data for regime detection
            fixture_data = {
                "home_team": f"team_{fixture.home_team_id}",
                "away_team": f"team_{fixture.away_team_id}",
                "competition_code": league_name,
                "utc_date": fixture.utc_date
            }
            
            # Mock evidence (would come from real data in production)
            evidence = [
                {"type": "home_advantage", "strength": 0.7, "direction": 1},
                {"type": "rest_days", "strength": 0.6, "direction": 1}
            ]
            
            # Use Intelligence Engine to process
            result = intell.process_prediction(
                model_probability=model_prob,
                market_odds=mock_odds,
                model_predictions=model_preds,
                fixture_data=fixture_data,
                evidence=evidence,
                bankroll=10000
            )
            
            # Determine actual outcome
            total_goals = (fixture.home_score or 0) + (fixture.away_score or 0)
            actual = 1 if total_goals > 2 else 0
            
            bet_result = {
                'fixture_id': fixture.id,
                'probability': result['final_probability'],
                'prediction': 1 if result['approved'] else 0,
                'stake': result['stake'],
                'odds': mock_odds,
                'actual': actual,
                'is_correct': (1 if result['approved'] else 0) == actual,
                'profit': 0,
                'regime': result['regime'],
                'confidence': result['confidence']
            }
            
            # Calculate profit if bet was placed
            if result['approved'] and result['stake'] > 0:
                if bet_result['is_correct']:
                    bet_result['profit'] = result['stake'] * (mock_odds - 1)
                else:
                    bet_result['profit'] = -result['stake']
                accepted_bets.append(bet_result)
            else:
                rejected_bets.append(bet_result)
        
        # Calculate results
        if accepted_bets:
            wins = sum(1 for b in accepted_bets if b['is_correct'])
            total_profit = sum(b['profit'] for b in accepted_bets)
            total_stake = sum(b['stake'] for b in accepted_bets)
            roi = (total_profit / total_stake * 100) if total_stake > 0 else 0
            
            print(f"\n    Intelligence Engine Results:")
            print(f"      Accepted Bets: {len(accepted_bets)}")
            print(f"      Win Rate: {wins/len(accepted_bets)*100:.1f}%")
            print(f"      Total Stake: ${total_stake:.2f}")
            print(f"      Total Profit: ${total_profit:+.2f}")
            print(f"      ROI: {roi:+.2f}%")
            
            # Show regime breakdown
            regimes = {}
            for b in accepted_bets:
                r = b['regime']
                if r not in regimes:
                    regimes[r] = {'bets': 0, 'profit': 0}
                regimes[r]['bets'] += 1
                regimes[r]['profit'] += b['profit']
            
            print(f"\n      By Regime:")
            for r, data in regimes.items():
                print(f"        {r}: {data['bets']} bets, ${data['profit']:+.2f}")
            
            results.append({
                'League': league_name,
                'Bets': len(accepted_bets),
                'Wins': wins,
                'WinRate': f"{wins/len(accepted_bets)*100:.1f}%",
                'Stake': f"${total_stake:.0f}",
                'Profit': f"${total_profit:+.2f}",
                'ROI': f"{roi:+.2f}%"
            })
        else:
            print(f"    No bets accepted by intelligence filter")

# Summary
print("\n" + "="*60)
print("  INTELLIGENCE ENGINE SUMMARY")
print("="*60)

df = pd.DataFrame(results)
if len(df) > 0:
    print("\n" + df.to_string(index=False))
    
    total_bets = sum(r['Bets'] for r in results)
    total_profit = sum(float(r['Profit'].replace('$','')) for r in results)
    total_stake = sum(float(r['Stake'].replace('$','')) for r in results)
    
    print(f"\nTotal: {total_bets} bets, ${total_profit:+.2f} profit, {(total_profit/total_stake*100):+.2f}% ROI")
else:
    print("\nNo results to display")

print("\n[COMPLETE]")
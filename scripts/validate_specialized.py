import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import numpy as np
from src.data.connection import DatabaseManager
from src.data.database import Fixture, Competition
from src.features.repository import FeatureRepository
from src.models.trainer import ModelTrainer
from src.models.evaluator import Backtester
from src.decisions.engine import DecisionEngine, LEAGUE_CONFIGS, ENABLED_LEAGUES
from src.utils.helpers import load_config
import warnings
warnings.filterwarnings('ignore')

config = load_config()
model_config = config.get('model', {})
feature_config = config.get('features', {})

db_manager = DatabaseManager.get_instance()
db_manager.initialize()

print('=== Phase 3 Final Validation: League-Specialized System ===\n')

# Test core leagues with specialized thresholds
total_profit = 0
total_bets = 0

for league_name in ENABLED_LEAGUES:
    comp_id = LEAGUE_CONFIGS[league_name]['competition_id']
    threshold = LEAGUE_CONFIGS[league_name]['threshold']
    
    with db_manager.session() as session:
        repo = FeatureRepository(session, feature_config)
        X, y = repo.get_training_data(competition_id=comp_id, target_column='target_over_25')
        
        trainer = ModelTrainer(model_config)
        trainer.feature_names = list(X.columns)
        X_train, X_test, y_train, y_test = trainer.prepare_data(X, y)
        
        # Train ensemble
        trainer.train_ensemble(X_train, y_train)
        
        # Get predictions
        y_prob = trainer.ensemble_proba(X_test)
        y_pred = trainer.ensemble_predict(X_test)
        
        # Use league-specific decision engine
        league_model_config = model_config.copy()
        league_model_config['min_confidence'] = threshold
        engine = DecisionEngine(league_model_config, league_code=league_name)
        
        # Make decisions using league-specific threshold
        decisions = []
        for prob in y_prob:
            is_accepted, conf, decision = engine.make_decision(prob, {})
            decisions.append(is_accepted)
        
        decisions = np.array(decisions)
        
        # Calculate results for accepted bets only
        accepted_mask = decisions == 1
        if accepted_mask.sum() > 0:
            accepted_preds = y_pred[accepted_mask]
            accepted_probs = y_prob[accepted_mask]
            accepted_actuals = y_test.values[accepted_mask]
            
            backtester = Backtester(initial_bankroll=1000.0/len(ENABLED_LEAGUES))
            results = backtester.run_backtest(
                predictions=accepted_preds,
                probabilities=accepted_probs,
                actuals=accepted_actuals,
                stake=1.0,
                confidence_threshold=threshold
            )
            
            print(f'{league_name}:')
            print(f'  Threshold: {threshold}')
            print(f'  Bets: {results["total_bets"]}')
            print(f'  Win Rate: {results["win_rate"]*100:.1f}%')
            print(f'  ROI: {results["roi"]:+.2f}%')
            print(f'  Profit: ${results["total_profit"]:.2f}')
            print()
            
            total_bets += results['total_bets']
            total_profit += results['total_profit']

print('=' * 50)
print(f'TOTAL: {total_bets} bets, ${total_profit:+.2f} profit')
print(f'Overall ROI: {(total_profit/1000)*100:+.2f}%')
print()
print('Core leagues (BL1, PL) are now optimized for production.')
print('Other leagues (PD, SA, FL1) are disabled for better risk-adjusted returns.')
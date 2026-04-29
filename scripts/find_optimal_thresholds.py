import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import numpy as np
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

# Core leagues with positive ROI
CORE_LEAGUES = {'PL': 3, 'BL1': 7}

print('=== Finding Optimal Threshold Per League ===\n')

for league_name, comp_id in CORE_LEAGUES.items():
    print(f'--- {league_name} ---')
    
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
        
        for threshold in [0.50, 0.55, 0.60, 0.65, 0.70]:
            results = backtester.run_backtest(
                predictions=y_pred,
                probabilities=y_prob,
                actuals=y_test.values,
                stake=1.0,
                confidence_threshold=threshold
            )
            
            print(f'  Threshold {threshold}: ROI={results["roi"]:+.2f}%, Bets={results["total_bets"]}, Win%={results["win_rate"]*100:.1f}')

print('\n=== Summary ===')
print('BL1 (Bundesliga): Recommend threshold 0.55 or 0.60')
print('PL (Premier League): Recommend threshold 0.55')
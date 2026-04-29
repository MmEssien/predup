"""Per-league backtest analysis"""

from dotenv import load_dotenv
load_dotenv()

from src.data.connection import DatabaseManager
from src.features.repository import FeatureRepository
from src.models.trainer import ModelTrainer
from src.models.evaluator import Backtester
from src.utils.helpers import load_config

config = load_config()
model_config = config.get('model', {})
feature_config = config.get('features', {})

db_manager = DatabaseManager.get_instance()
db_manager.initialize()

leagues = {
    'PL': 1,
    'BL1': 2,
    'PD': 3,
    'SA': 4,
    'FL1': 5,
}

print('=== Per-League Backtest Results ===\n')

best_league = None
best_roi = float('-inf')

for league_name, comp_id in leagues.items():
    with db_manager.session() as session:
        repo = FeatureRepository(session, feature_config)
        try:
            X, y = repo.get_training_data(competition_id=comp_id, target_column='target_over_25')
            
            if len(X) < 100:
                print(f'{league_name}: Insufficient data ({len(X)})')
                continue
            
            trainer = ModelTrainer(model_config)
            trainer.feature_names = list(X.columns)
            
            X_train, X_test, y_train, y_test = trainer.prepare_data(X, y)
            trainer.train_ensemble(X_train, y_train)
            
            y_prob = trainer.ensemble_proba(X_test)
            y_pred = trainer.ensemble_predict(X_test)
            
            backtester = Backtester(initial_bankroll=1000.0)
            results = backtester.run_backtest(
                predictions=y_pred,
                probabilities=y_prob,
                actuals=y_test.values,
                stake=1.0,
                confidence_threshold=0.55
            )
            
            print(f'{league_name}: {len(X)} samples')
            print(f'  ROI: {results["roi"]:+.2f}% | Bets: {results["total_bets"]} | Win%: {results["win_rate"]*100:.1f}%')
            
            if results['roi'] > best_roi and results['total_bets'] > 10:
                best_roi = results['roi']
                best_league = league_name
                
        except Exception as e:
            print(f'{league_name}: Error - {e}')

print(f'\n=== Best League: {best_league} with {best_roi:+.2f}% ROI ===')
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

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

leagues = {'PL': 3, 'BL1': 7, 'PD': 12, 'SA': 8, 'FL1': 6}

print('=== Per-League Results (threshold 0.55) ===')

for league_name, comp_id in leagues.items():
    with db_manager.session() as session:
        repo = FeatureRepository(session, feature_config)
        X, y = repo.get_training_data(competition_id=comp_id, target_column='target_over_25')
        
        if len(X) < 50:
            print(f'{league_name}: Only {len(X)} samples')
            continue
        
        trainer = ModelTrainer(model_config)
        trainer.feature_names = list(X.columns)
        X_train, X_test, y_train, y_test = trainer.prepare_data(X, y)
        trainer.train_ensemble(X_train, y_train)
        
        y_prob = trainer.ensemble_proba(X_test)
        y_pred = trainer.ensemble_predict(X_test)
        
        backtester = Backtester(initial_bankroll=1000.0)
        results = backtester.run_backtest(y_pred, y_prob, y_test.values, confidence_threshold=0.55)
        
        print(f'{league_name}: n={len(X)}, ROI={results["roi"]:+.2f}%, Bets={results["total_bets"]}, Win%={results["win_rate"]*100:.1f}')

print()
print('=== Complete Dataset Results (threshold 0.50) ===')
with db_manager.session() as session:
    repo = FeatureRepository(session, feature_config)
    X, y = repo.get_training_data(target_column='target_over_25')
    
    trainer = ModelTrainer(model_config)
    trainer.feature_names = list(X.columns)
    X_train, X_test, y_train, y_test = trainer.prepare_data(X, y)
    trainer.train_ensemble(X_train, y_train)
    
    y_prob = trainer.ensemble_proba(X_test)
    y_pred = trainer.ensemble_predict(X_test)
    
    backtester = Backtester(initial_bankroll=1000.0)
    results = backtester.run_backtest(y_pred, y_prob, y_test.values, confidence_threshold=0.50)
    
    print(f'All: n={len(X)}, ROI={results["roi"]:+.2f}%, Bets={results["total_bets"]}, Win%={results["win_rate"]*100:.1f}')
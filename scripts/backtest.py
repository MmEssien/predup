"""Backtest script for model evaluation"""

import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.connection import DatabaseManager
from src.features.repository import FeatureRepository
from src.models.trainer import ModelTrainer
from src.models.evaluator import Backtester
from src.utils.helpers import load_config
import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def backtest(
    target_column: str = "target_over_25",
    competition_id: int = None,
    confidence_threshold: float = 0.75,
    stake: float = 1.0
):
    """Run backtest on historical predictions"""
    config = load_config()
    feature_config = config.get("features", {})
    model_config = config.get("model", {})

    db_manager = DatabaseManager.get_instance()
    db_manager.initialize()

    logger.info("Loading training data...")

    with db_manager.session() as session:
        repo = FeatureRepository(session, feature_config)
        X, y = repo.get_training_data(
            competition_id=competition_id,
            target_column=target_column
        )

        logger.info(f"Data: {len(X)} samples")

        if len(X) < 100:
            logger.error("Insufficient data for backtest")
            return

        trainer = ModelTrainer(model_config)
        trainer.feature_names = list(X.columns)

        X_train, X_test, y_train, y_test = trainer.prepare_data(X, y)

        logger.info("Training ensemble...")

        trainer.train_ensemble(X_train, y_train)

        logger.info("Running backtest...")

        y_prob = trainer.ensemble_proba(X_test)
        y_pred = trainer.predict(X_test)
        ensemble_pred = trainer.ensemble_predict(X_test)

        backtester = Backtester(initial_bankroll=1000.0)

        results = backtester.run_backtest(
            predictions=ensemble_pred,
            probabilities=y_prob,
            actuals=y_test.values,
            stake=stake,
            confidence_threshold=confidence_threshold
        )

        logger.info("\nBacktest Results:")
        logger.info("=" * 40)
        logger.info(f"Initial bankroll: ${results['initial_bankroll']:.2f}")
        logger.info(f"Final bankroll: ${results['final_bankroll']:.2f}")
        logger.info(f"Profit: ${results['total_profit']:.2f}")
        logger.info(f"ROI: {results['roi']:.2f}%")
        logger.info(f"Total bets: {results['total_bets']}")
        logger.info(f"Win rate: {results['win_rate']:.2%}")

        dd = backtester.get_drawdown()
        logger.info(f"Max drawdown: {dd:.2f}%")

        bet_history = backtester.get_bet_history()

        logger.info("\nBet Distribution:")
        logger.info(f"  Winning bets: {results['winning_bets']}")
        logger.info(f"  Losing bets: {results['losing_bets']}")

        return results, bet_history


def find_optimal_threshold(
    target_column: str = "target_over_25",
    competition_id: int = None,
    thresholds: list = None
):
    """Find optimal confidence threshold"""
    if thresholds is None:
        thresholds = [0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9]

    config = load_config()
    feature_config = config.get("features", {})
    model_config = config.get("model", {})

    db_manager = DatabaseManager.get_instance()
    db_manager.initialize()

    with db_manager.session() as session:
        repo = FeatureRepository(session, feature_config)
        X, y = repo.get_training_data(
            competition_id=competition_id,
            target_column=target_column
        )

        trainer = ModelTrainer(model_config)
        trainer.feature_names = list(X.columns)

        X_train, X_test, y_train, y_test = trainer.prepare_data(X, y)
        trainer.train_ensemble(X_train, y_train)

        logger.info("\nThreshold Optimization:")
        logger.info("=" * 60)
        logger.info(f"{'Threshold':<12} {'Bets':<8} {'Win%':<8} {'ROI':<10} {'Profit':<10}")
        logger.info("-" * 60)

        best_threshold = 0.5
        best_roi = float("-inf")

        for threshold in thresholds:
            backtester = Backtester(initial_bankroll=1000.0)

            y_prob = trainer.ensemble_proba(X_test)
            y_pred = trainer.ensemble_predict(X_test)

            results = backtester.run_backtest(
                predictions=y_pred,
                probabilities=y_prob,
                actuals=y_test.values,
                confidence_threshold=threshold
            )

            logger.info(
                f"{threshold:<12.2f} {results['total_bets']:<8} "
                f"{results['win_rate']:<8.2%} {results['roi']:<10.2f} "
                f"${results['total_profit']:<10.2f}"
            )

            if results["roi"] > best_roi:
                best_roi = results["roi"]
                best_threshold = threshold

        logger.info("-" * 60)
        logger.info(f"Best threshold: {best_threshold:.2f} (ROI: {best_roi:.2f}%)")

        return best_threshold


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Backtest model")
    parser.add_argument("--run", action="store_true", help="Run backtest")
    parser.add_argument("--optimize", action="store_true", help="Optimize threshold")
    parser.add_argument("--target", type=str, default="target_over_25", help="Target column")
    parser.add_argument("--competition", type=int, help="Competition ID")
    parser.add_argument("--threshold", type=float, default=0.75, help="Confidence threshold")
    parser.add_argument("--stake", type=float, default=1.0, help="Stake amount")
    args = parser.parse_args()

    if args.run:
        backtest(
            target_column=args.target,
            competition_id=args.competition,
            confidence_threshold=args.threshold,
            stake=args.stake
        )
    elif args.optimize:
        find_optimal_threshold(
            target_column=args.target,
            competition_id=args.competition
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
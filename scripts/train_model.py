"""Model training script"""

import sys
import logging
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.connection import DatabaseManager
from src.features.repository import FeatureRepository
from src.models.trainer import ModelTrainer
from src.models import create_registry
from src.utils.helpers import load_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def train_model(
    target_column: str = "target_over_25",
    competition_id: int = None,
    save_model: bool = True,
    model_name: str = "predictions"
):
    """Train prediction model"""
    config = load_config()
    model_config = config.get("model", {})
    feature_config = config.get("features", {})

    db_manager = DatabaseManager.get_instance()
    db_manager.initialize()

    logger.info("Loading training data...")

    with db_manager.session() as session:
        repo = FeatureRepository(session, feature_config)
        X, y = repo.get_training_data(
            competition_id=competition_id,
            target_column=target_column
        )

        logger.info(f"Training data: {len(X)} samples")

        if len(X) < 50:
            logger.error("Insufficient training data")
            return None

        trainer = ModelTrainer(model_config)
        trainer.feature_names = list(X.columns)

        X_train, X_test, y_train, y_test = trainer.prepare_data(X, y)

        logger.info("Training ensemble models...")

        trainer.train_ensemble(X_train, y_train)

        logger.info("Evaluating on test set...")

        results = trainer.evaluate(X_test, y_test)

        for name, metrics in results.items():
            logger.info(f"\n{name}:")
            for metric, value in metrics.items():
                logger.info(f"  {metric}: {value:.4f}")

        if save_model:
            for model_key in ["xgboost", "lightgbm"]:
                if model_key in trainer.models:
                    version = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

                    registry = create_registry("models")
                    registry.register_model(
                        model_name=model_key,
                        model=trainer.models[model_key],
                        version=version,
                        metrics=results.get(model_key, {}),
                        feature_names=trainer.feature_names,
                        config=model_config
                    )

                    logger.info(f"Saved {model_key} version {version}")

        return trainer, results


def cross_validate(
    target_column: str = "target_over_25",
    competition_id: int = None,
    cv: int = 5
):
    """Cross-validate models"""
    config = load_config()
    feature_config = config.get("features", {})

    db_manager = DatabaseManager.get_instance()
    db_manager.initialize()

    with db_manager.session() as session:
        repo = FeatureRepository(session, feature_config)
        X, y = repo.get_training_data(
            competition_id=competition_id,
            target_column=target_column
        )

        trainer = ModelTrainer(config.get("model", {}))
        trainer.feature_names = list(X.columns)

        logger.info(f"Cross-validating with {cv} folds...")

        for model_name in ["xgboost", "lightgbm", "logreg"]:
            cv_results = trainer.cross_validate(X, y, model_name, cv=cv)

            if cv_results:
                logger.info(f"\n{model_name}:")
                logger.info(f"  Mean accuracy: {cv_results.get('cv_mean', 0):.4f}")
                logger.info(f"  Std: {cv_results.get('cv_std', 0):.4f}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Model training")
    parser.add_argument("--train", action="store_true", help="Train model")
    parser.add_argument("--cv", action="store_true", help="Cross-validate")
    parser.add_argument("--target", type=str, default="target_over_25", help="Target column")
    parser.add_argument("--competition", type=int, help="Competition ID")
    parser.add_argument("--model-name", type=str, default="predictions", help="Model name")
    parser.add_argument("--folds", type=int, default=5, help="CV folds")
    parser.add_argument("--no-save", action="store_true", help="Don't save model")
    args = parser.parse_args()

    if args.train:
        train_model(
            target_column=args.target,
            competition_id=args.competition,
            save_model=not args.no_save,
            model_name=args.model_name
        )
    elif args.cv:
        cross_validate(
            target_column=args.target,
            competition_id=args.competition,
            cv=args.folds
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
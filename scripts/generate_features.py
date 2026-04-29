"""Feature generation script"""

import sys
import logging
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.connection import DatabaseManager
from src.features.repository import FeatureRepository
from src.utils.helpers import load_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def generate_training_dataset(
    competition_id: int = None,
    start_date: str = None,
    end_date: str = None,
    target: str = "target_over_25",
    save_path: str = None
):
    """Generate training dataset"""
    config = load_config()
    db_manager = DatabaseManager.get_instance()
    db_manager.initialize()

    with db_manager.session() as session:
        repo = FeatureRepository(session, config.get("features", {}))

        min_date = datetime.fromisoformat(start_date) if start_date else None
        max_date = datetime.fromisoformat(end_date) if end_date else None

        logger.info("Generating training dataset...")
        X, y = repo.get_training_data(
            competition_id=competition_id,
            min_date=min_date,
            max_date=max_date,
            target_column=target
        )

        logger.info(f"Dataset: {len(X)} samples, {len(X.columns)} features")

        if save_path:
            df = X.copy()
            df[target] = y
            df.to_csv(save_path, index=False)
            logger.info(f"Saved dataset to {save_path}")

        return X, y


def validate_features(save_path: str = None):
    """Validate feature quality"""
    config = load_config()
    db_manager = DatabaseManager.get_instance()
    db_manager.initialize()

    with db_manager.session() as session:
        repo = FeatureRepository(session, config.get("features", {}))

        logger.info("Validating features...")
        df = repo.get_training_data(competition_id=None)[0]

        report = repo.validate_features(df)

        logger.info(f"Total features: {report['total_features']}")
        logger.info(f"Features with nulls: {len(report['null_counts'])}")
        logger.info(f"Zero variance features: {len(report['zero_variance'])}")
        logger.info(f"High correlation pairs: {len(report['high_correlation_pairs'])}")

        if save_path:
            import json
            with open(save_path, "w") as f:
                json.dump(report, f, indent=2)

        return report


def generate_upcoming_features(days_ahead: int = 7, save_path: str = None):
    """Generate features for upcoming fixtures"""
    config = load_config()
    db_manager = DatabaseManager.get_instance()
    db_manager.initialize()

    with db_manager.session() as session:
        repo = FeatureRepository(session, config.get("features", {}))

        logger.info(f"Generating features for {days_ahead} days...")
        df = repo.get_upcoming_features(days_ahead=days_ahead)

        logger.info(f"Found {len(df)} upcoming fixtures")

        if save_path:
            df.to_csv(save_path, index=False)
            logger.info(f"Saved features to {save_path}")

        return df


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Feature generation")
    parser.add_argument("--generate-train", action="store_true", help="Generate training dataset")
    parser.add_argument("--validate", action="store_true", help="Validate features")
    parser.add_argument("--upcoming", action="store_true", help="Generate upcoming features")
    parser.add_argument("--competition", type=int, help="Competition ID")
    parser.add_argument("--start", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, help="End date (YYYY-MM-DD)")
    parser.add_argument("--target", type=str, default="target_over_25", help="Target column")
    parser.add_argument("--output", type=str, help="Output CSV path")
    parser.add_argument("--days", type=int, default=7, help="Days ahead for upcoming")
    args = parser.parse_args()

    if args.generate_train:
        generate_training_dataset(
            competition_id=args.competition,
            start_date=args.start,
            end_date=args.end,
            target=args.target,
            save_path=args.output
        )
    elif args.validate:
        validate_features(save_path=args.output)
    elif args.upcoming:
        generate_upcoming_features(days_ahead=args.days, save_path=args.output)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
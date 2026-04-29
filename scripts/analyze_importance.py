"""Feature importance analysis script"""

import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.connection import DatabaseManager
from src.features.repository import FeatureRepository
from src.utils.helpers import load_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def analyze_importance(competition_id: int = None, n_estimators: int = 100, top_n: int = 20):
    """Analyze feature importance"""
    config = load_config()
    db_manager = DatabaseManager.get_instance()
    db_manager.initialize()

    with db_manager.session() as session:
        repo = FeatureRepository(session, config.get("features", {}))

        logger.info("Calculating feature importance...")
        importance = repo.get_feature_importance(
            competition_id=competition_id,
            n_estimators=n_estimators
        )

        if importance.empty:
            logger.warning("No training data available")
            return

        logger.info(f"\nTop {top_n} Features:")
        logger.info("-" * 40)

        for i, row in importance.head(top_n).iterrows():
            logger.info(f"{row['feature']}: {row['importance']:.4f}")

        return importance


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Feature importance analysis")
    parser.add_argument("--competition", type=int, help="Competition ID")
    parser.add_argument("--n-estimators", type=int, default=100, help="Number of estimators")
    parser.add_argument("--top", type=int, default=20, help="Top N features")
    parser.add_argument("--output", type=str, help="Output CSV path")
    args = parser.parse_args()

    importance = analyze_importance(
        competition_id=args.competition,
        n_estimators=args.n_estimators,
        top_n=args.top
    )

    if args.output and not importance.empty:
        importance.to_csv(args.output, index=False)
        logger.info(f"Saved to {args.output}")


if __name__ == "__main__":
    main()
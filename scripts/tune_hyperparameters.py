"""Hyperparameter tuning script for XGBoost and LightGBM"""

import sys
import logging
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from src.data.connection import DatabaseManager
from src.features.repository import FeatureRepository
from src.utils.helpers import load_config
import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def tune_xgboost(X_train, y_train, cv=5):
    """Tune XGBoost hyperparameters using RandomizedSearchCV"""
    try:
        from xgboost import XGBClassifier
        from sklearn.model_selection import RandomizedSearchCV
    except ImportError:
        logger.error("xgboost not installed")
        return None

    param_distributions = {
        "n_estimators": [100, 200, 300, 500],
        "max_depth": [3, 4, 5, 6, 7],
        "learning_rate": [0.01, 0.05, 0.1, 0.15],
        "min_child_weight": [1, 3, 5, 7],
        "subsample": [0.6, 0.7, 0.8, 0.9],
        "colsample_bytree": [0.6, 0.7, 0.8, 0.9],
        "gamma": [0, 0.1, 0.2, 0.3],
        "reg_alpha": [0, 0.01, 0.1, 1],
        "reg_lambda": [1, 1.5, 2, 3],
    }

    base_model = XGBClassifier(
        random_state=42,
        eval_metric="logloss",
        use_label_encoder=False
    )

    search = RandomizedSearchCV(
        base_model,
        param_distributions,
        n_iter=30,
        cv=cv,
        scoring="roc_auc",
        n_jobs=-1,
        verbose=1,
        random_state=42
    )

    logger.info("Tuning XGBoost hyperparameters...")
    search.fit(X_train, y_train)

    logger.info(f"Best XGBoost params: {search.best_params_}")
    logger.info(f"Best XGBoost CV score: {search.best_score_:.4f}")

    return search.best_params_, search.best_score_


def tune_lightgbm(X_train, y_train, cv=5):
    """Tune LightGBM hyperparameters using RandomizedSearchCV"""
    try:
        from lightgbm import LGBMClassifier
        from sklearn.model_selection import RandomizedSearchCV
    except ImportError:
        logger.error("lightgbm not installed")
        return None

    param_distributions = {
        "n_estimators": [100, 200, 300, 500],
        "max_depth": [3, 4, 5, 6, 7, -1],
        "learning_rate": [0.01, 0.05, 0.1, 0.15],
        "num_leaves": [15, 31, 63, 127],
        "min_child_samples": [10, 20, 30, 50],
        "subsample": [0.6, 0.7, 0.8, 0.9],
        "colsample_bytree": [0.6, 0.7, 0.8, 0.9],
        "reg_alpha": [0, 0.01, 0.1, 1],
        "reg_lambda": [0, 0.01, 0.1, 1],
    }

    base_model = LGBMClassifier(
        random_state=42,
        verbose=-1
    )

    search = RandomizedSearchCV(
        base_model,
        param_distributions,
        n_iter=30,
        cv=cv,
        scoring="roc_auc",
        n_jobs=-1,
        verbose=1,
        random_state=42
    )

    logger.info("Tuning LightGBM hyperparameters...")
    search.fit(X_train, y_train)

    logger.info(f"Best LightGBM params: {search.best_params_}")
    logger.info(f"Best LightGBM CV score: {search.best_score_:.4f}")

    return search.best_params_, search.best_score_


def main():
    config = load_config()
    feature_config = config.get("features", {})

    db_manager = DatabaseManager.get_instance()
    db_manager.initialize()

    logger.info("Loading training data...")
    with db_manager.session() as session:
        repo = FeatureRepository(session, feature_config)
        X, y = repo.get_training_data(
            competition_id=None,
            target_column="target_over_25"
        )

    logger.info(f"Data: {len(X)} samples, {len(X.columns)} features")

    # Tune both models
    results = {}

    xgb_params, xgb_score = tune_xgboost(X, y, cv=3)
    results["xgboost"] = {
        "best_params": xgb_params,
        "cv_score": xgb_score
    }

    lgb_params, lgb_score = tune_lightgbm(X, y, cv=3)
    results["lightgbm"] = {
        "best_params": lgb_params,
        "cv_score": lgb_score
    }

    # Save results
    output_path = "models/hyperparams_results.json"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    logger.info(f"Results saved to {output_path}")
    logger.info(f"Best XGBoost: {xgb_score:.4f}")
    logger.info(f"Best LightGBM: {lgb_score:.4f}")

    return results


if __name__ == "__main__":
    main()
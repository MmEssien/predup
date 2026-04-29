"""Model training module for PredUp - with calibration and Kelly criterion"""

import logging
import json
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from pathlib import Path
import pickle
import pandas as pd
import numpy as np

from sklearn.model_selection import train_test_split, cross_val_score, TimeSeriesSplit
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, log_loss, confusion_matrix, classification_report
)

logger = logging.getLogger(__name__)


class ModelTrainer:
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.models: Dict[str, Any] = {}
        self.feature_names: List[str] = []
        self.training_history: Dict[str, List[Dict]] = {}

    def prepare_data(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        test_size: float = None,
        random_state: int = None
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
        test_size = test_size or self.config.get("test_split", 0.3)
        random_state = random_state or self.config.get("random_state", 42)

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_state, stratify=y
        )

        logger.info(f"Training samples: {len(X_train)}, Test samples: {len(X_test)}")

        return X_train, X_test, y_train, y_test

    def prepare_time_series(self, X: pd.DataFrame, y: pd.Series, n_splits: int = 5) -> TimeSeriesSplit:
        tscv = TimeSeriesSplit(n_splits=n_splits)
        return tscv

    def train_xgboost(self, X_train: pd.DataFrame, y_train: pd.Series,
                      X_val: Optional[pd.DataFrame] = None, y_val: Optional[pd.Series] = None,
                      params: Optional[Dict] = None) -> Any:
        try:
            from xgboost import XGBClassifier
        except ImportError:
            logger.error("xgboost not installed")
            return None

        default_params = {
            "n_estimators": 100,
            "max_depth": 5,
            "learning_rate": 0.1,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "random_state": self.config.get("random_state", 42),
            "use_label_encoder": False,
            "eval_metric": "logloss",
        }

        if params:
            default_params.update(params)

        model = XGBClassifier(**default_params)

        if X_val is not None and y_val is not None:
            model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
        else:
            model.fit(X_train, y_train)

        self.models["xgboost"] = model
        logger.info("XGBoost model trained")

        return model

    def train_lightgbm(self, X_train: pd.DataFrame, y_train: pd.Series,
                        X_val: Optional[pd.DataFrame] = None, y_val: Optional[pd.Series] = None,
                        params: Optional[Dict] = None) -> Any:
        try:
            from lightgbm import LGBMClassifier
        except ImportError:
            logger.error("lightgbm not installed")
            return None

        default_params = {
            "n_estimators": 100,
            "max_depth": 5,
            "learning_rate": 0.1,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "random_state": self.config.get("random_state", 42),
            "verbose": -1,
        }

        if params:
            default_params.update(params)

        model = LGBMClassifier(**default_params)

        if X_val is not None and y_val is not None:
            model.fit(X_train, y_train, eval_set=[(X_val, y_val)])
        else:
            model.fit(X_train, y_train)

        self.models["lightgbm"] = model
        logger.info("LightGBM model trained")

        return model

    def train_logistic_regression(self, X_train: pd.DataFrame, y_train: pd.Series,
                                   params: Optional[Dict] = None) -> Any:
        default_params = {
            "C": 1.0,
            "max_iter": 1000,
            "random_state": self.config.get("random_state", 42),
        }

        if params:
            default_params.update(params)

        model = LogisticRegression(**default_params)
        model.fit(X_train, y_train)

        self.models["logreg"] = model
        logger.info("Logistic Regression model trained")

        return model

    def train_ensemble(self, X_train: pd.DataFrame, y_train: pd.Series,
                       X_val: Optional[pd.DataFrame] = None, y_val: Optional[pd.Series] = None,
                       models: Optional[List[str]] = None) -> Dict[str, Any]:
        models = models or ["xgboost", "lightgbm", "logreg"]
        trained = {}

        for model_name in models:
            try:
                if model_name == "xgboost":
                    model = self.train_xgboost(X_train, y_train, X_val, y_val)
                elif model_name == "lightgbm":
                    model = self.train_lightgbm(X_train, y_train, X_val, y_val)
                elif model_name == "logreg":
                    model = self.train_logistic_regression(X_train, y_train)

                if model:
                    trained[model_name] = model
            except Exception as e:
                logger.error(f"Error training {model_name}: {e}")

        return trained

    def predict(self, X: pd.DataFrame, model_names: Optional[List[str]] = None) -> Dict[str, np.ndarray]:
        if model_names is None:
            model_names = list(self.models.keys())

        predictions = {}

        for name in model_names:
            if name in self.models:
                predictions[name] = self.models[name].predict(X)

        return predictions

    def predict_proba(self, X: pd.DataFrame, model_names: Optional[List[str]] = None) -> Dict[str, np.ndarray]:
        if model_names is None:
            model_names = list(self.models.keys())

        probabilities = {}

        for name in model_names:
            if name in self.models and hasattr(self.models[name], "predict_proba"):
                probabilities[name] = self.models[name].predict_proba(X)[:, 1]

        return probabilities

    def ensemble_predict(self, X: pd.DataFrame, weights: Optional[Dict[str, float]] = None) -> np.ndarray:
        weights = weights or self.config.get("ensemble_weights", {
            "xgboost": 0.4,
            "lightgbm": 0.4,
            "logreg": 0.2,
        })

        probs = self.predict_proba(X, list(weights.keys()))

        if not probs:
            raise ValueError("No model predictions available")

        ensemble_prob = np.zeros_like(list(probs.values())[0])

        for name, weight in weights.items():
            if name in probs:
                ensemble_prob += weight * probs[name]

        return (ensemble_prob >= 0.5).astype(int)

    def ensemble_proba(self, X: pd.DataFrame, weights: Optional[Dict[str, float]] = None) -> np.ndarray:
        weights = weights or self.config.get("ensemble_weights", {
            "xgboost": 0.4,
            "lightgbm": 0.4,
            "logreg": 0.2,
        })

        probs = self.predict_proba(X, list(weights.keys()))

        if not probs:
            raise ValueError("No model predictions available")

        ensemble_prob = np.zeros_like(list(probs.values())[0])

        for name, weight in weights.items():
            if name in probs:
                ensemble_prob += weight * probs[name]

        return ensemble_prob

    def evaluate(self, X: pd.DataFrame, y: pd.Series, model_names: Optional[List[str]] = None) -> Dict[str, Dict[str, float]]:
        if model_names is None:
            model_names = list(self.models.keys())

        results = {}

        for name in model_names:
            if name not in self.models:
                continue

            y_pred = self.models[name].predict(X)

            results[name] = {
                "accuracy": accuracy_score(y, y_pred),
                "precision": precision_score(y, y_pred, zero_division=0),
                "recall": recall_score(y, y_pred, zero_division=0),
                "f1": f1_score(y, y_pred, zero_division=0),
            }

            if hasattr(self.models[name], "predict_proba"):
                try:
                    y_prob = self.models[name].predict_proba(X)[:, 1]
                    results[name]["roc_auc"] = roc_auc_score(y, y_prob)
                    results[name]["log_loss"] = log_loss(y, y_prob)
                except:
                    pass

        return results

    def cross_validate(self, X: pd.DataFrame, y: pd.Series, model_name: str = "xgboost", cv: int = 5) -> Dict[str, float]:
        if model_name == "xgboost" and "xgboost" not in self.models:
            try:
                from xgboost import XGBClassifier
            except ImportError:
                return {}

            model = XGBClassifier(n_estimators=100, max_depth=5, random_state=self.config.get("random_state", 42))
        elif model_name == "lightgbm" and "lightgbm" not in self.models:
            try:
                from lightgbm import LGBMClassifier
            except ImportError:
                return {}

            model = LGBMClassifier(n_estimators=100, max_depth=5, random_state=self.config.get("random_state", 42))
        else:
            model = self.models.get(model_name)

        if model is None:
            return {}

        scores = cross_val_score(model, X, y, cv=cv, scoring="accuracy")

        return {"cv_mean": scores.mean(), "cv_std": scores.std(), "cv_scores": scores.tolist()}

    def save_model(self, model_name: str, path: str, include_config: bool = True) -> None:
        if model_name not in self.models:
            raise ValueError(f"Model {model_name} not found")

        model_data = {
            "model": self.models[model_name],
            "feature_names": self.feature_names,
            "trained_at": datetime.utcnow().isoformat(),
        }

        if include_config:
            model_data["config"] = self.config

        with open(path, "wb") as f:
            pickle.dump(model_data, f)

        logger.info(f"Saved {model_name} to {path}")

    def load_model(self, model_name: str, path: str) -> Any:
        with open(path, "rb") as f:
            model_data = pickle.load(f)

        self.models[model_name] = model_data["model"]
        self.feature_names = model_data.get("feature_names", [])

        logger.info(f"Loaded {model_name} from {path}")

        return self.models[model_name]

    def get_feature_importance(self, model_name: str = "xgboost") -> pd.DataFrame:
        if model_name not in self.models:
            return pd.DataFrame()

        model = self.models[model_name]

        if hasattr(model, "feature_importances_"):
            return pd.DataFrame({"feature": self.feature_names, "importance": model.feature_importances_}).sort_values("importance", ascending=False)
        elif hasattr(model, "coef_"):
            return pd.DataFrame({"feature": self.feature_names, "importance": np.abs(model.coef_[0])}).sort_values("importance", ascending=False)

        return pd.DataFrame()


class HyperparameterTuner:
    def __init__(self, method: str = "grid"):
        self.method = method
        self.best_params: Dict = {}
        self.best_score: float = 0.0

    def tune_xgboost(self, X: pd.DataFrame, y: pd.Series, params_grid: Optional[Dict] = None, cv: int = 3) -> Dict:
        try:
            from xgboost import XGBClassifier
            from sklearn.model_selection import GridSearchCV
        except ImportError:
            return {}

        default_grid = {
            "n_estimators": [50, 100, 200],
            "max_depth": [3, 5, 7],
            "learning_rate": [0.01, 0.1, 0.2],
            "subsample": [0.7, 0.8, 0.9],
        }

        params_grid = params_grid or default_grid

        model = XGBClassifier(random_state=42, use_label_encoder=False, eval_metric="logloss")

        grid_search = GridSearchCV(model, params_grid, cv=cv, scoring="roc_auc", n_jobs=-1, verbose=1)

        grid_search.fit(X, y)

        self.best_params = grid_search.best_params_
        self.best_score = grid_search.best_score_

        logger.info(f"Best params: {self.best_params}")
        logger.info(f"Best score: {self.best_score:.4f}")

        return self.best_params

    def tune_lgbm(self, X: pd.DataFrame, y: pd.Series, params_grid: Optional[Dict] = None, cv: int = 3) -> Dict:
        try:
            from lightgbm import LGBMClassifier
            from sklearn.model_selection import GridSearchCV
        except ImportError:
            return {}

        default_grid = {
            "n_estimators": [50, 100, 200],
            "max_depth": [3, 5, 7],
            "learning_rate": [0.01, 0.1, 0.2],
            "num_leaves": [15, 31, 63],
        }

        params_grid = params_grid or default_grid

        model = LGBMClassifier(random_state=42, verbose=-1)

        grid_search = GridSearchCV(model, params_grid, cv=cv, scoring="roc_auc", n_jobs=-1, verbose=1)

        grid_search.fit(X, y)

        self.best_params = grid_search.best_params_
        self.best_score = grid_search.best_score_

        logger.info(f"Best params: {self.best_params}")
        logger.info(f"Best score: {self.best_score:.4f}")

        return self.best_params


class ModelCalibrator:
    """Calibration methods for probability outputs"""

    def __init__(self):
        self.calibrators = {}

    def calibrate_isotonic(self, X_train, y_train):
        from sklearn.calibration import CalibratedClassifierCV
        return CalibratedClassifierCV(LogisticRegression(max_iter=1000), method="isotonic", cv=3).fit(X_train, y_train)

    def calibrate_platt(self, X_train, y_train):
        from sklearn.calibration import CalibratedClassifierCV
        return CalibratedClassifierCV(LogisticRegression(max_iter=1000), method="sigmoid", cv=3).fit(X_train, y_train)

    def evaluate_calibration(self, y_true, y_prob, n_bins=10):
        bin_edges = np.linspace(0, 1, n_bins + 1)
        ece = 0

        for i in range(n_bins):
            mask = (y_prob >= bin_edges[i]) & (y_prob < bin_edges[i + 1])
            if mask.sum() > 0:
                bin_acc = y_true[mask].mean()
                bin_conf = y_prob[mask].mean()
                ece += (mask.sum() / len(y_true)) * abs(bin_acc - bin_conf)

        return ece


class KellyCriterion:
    """Kelly criterion for optimal stake sizing"""

    def __init__(self, fraction: float = 0.25, max_kelly: float = 0.02):
        self.fraction = fraction
        self.max_kelly = max_kelly

    def calculate_stake(self, probability: float, odds: float, bankroll: float = 1000.0) -> float:
        if odds <= 1:
            return 0

        b = odds - 1
        p = probability
        q = 1 - p

        kelly = (b * p - q) / b
        kelly = kelly * self.fraction
        kelly = max(0, kelly)
        kelly = min(kelly, self.max_kelly)

        return kelly * bankroll

    def calculate_stake_matrix(self, probabilities: np.ndarray, odds: float, bankroll: float = 1000.0) -> np.ndarray:
        return np.array([self.calculate_stake(p, odds, bankroll) for p in probabilities])

    def get_recommendation(self, probability: float, odds: float) -> str:
        stake = self.calculate_stake(probability, odds)
        if stake <= 0:
            return "NO BET"
        elif stake < 1:
            return "SMALL"
        elif stake < 2:
            return "MEDIUM"
        else:
            return "LARGE"
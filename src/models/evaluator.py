"""Model evaluation module for PredUp"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import json
import pandas as pd
import numpy as np

from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, log_loss, confusion_matrix, brier_score_loss,
    average_precision_score, balanced_accuracy_score
)

logger = logging.getLogger(__name__)


class ModelEvaluator:
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.evaluation_history: List[Dict] = []

    def evaluate_classification(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        y_prob: Optional[np.ndarray] = None,
        model_name: str = "model"
    ) -> Dict[str, float]:
        """Evaluate classification model"""
        metrics = {
            "accuracy": accuracy_score(y_true, y_pred),
            "precision": precision_score(y_true, y_pred, zero_division=0),
            "recall": recall_score(y_true, y_pred, zero_division=0),
            "f1": f1_score(y_true, y_pred, zero_division=0),
            "balanced_accuracy": balanced_accuracy_score(y_true, y_pred),
        }

        cm = confusion_matrix(y_true, y_pred)
        metrics["true_negatives"] = int(cm[0, 0])
        metrics["false_positives"] = int(cm[0, 1])
        metrics["false_negatives"] = int(cm[1, 0])
        metrics["true_positives"] = int(cm[1, 1])

        if y_prob is not None:
            metrics["roc_auc"] = roc_auc_score(y_true, y_prob)
            metrics["log_loss"] = log_loss(y_true, y_prob)
            metrics["brier_score"] = brier_score_loss(y_true, y_prob)
            metrics["average_precision"] = average_precision_score(y_true, y_prob)

        evaluation = {
            "model_name": model_name,
            "timestamp": datetime.utcnow().isoformat(),
            "n_samples": len(y_true),
            "metrics": metrics,
        }

        self.evaluation_history.append(evaluation)

        return metrics

    def calculate_profit(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        odds: Optional[np.ndarray] = None,
        stake: float = 1.0,
        confidence_threshold: float = 0.75
    ) -> Dict[str, float]:
        """Calculate profit metrics"""
        if odds is None:
            odds = np.ones_like(y_true) * 2.0

        correct = y_true == y_pred
        profit = 0.0
        total_staked = 0

        for i in range(len(y_true)):
            if y_pred[i] == 1:
                total_staked += stake
                if correct[i]:
                    profit += stake * (odds[i] - 1)
                else:
                    profit -= stake

        roi = (profit / total_staked * 100) if total_staked > 0 else 0

        return {
            "total_staked": total_staked,
            "profit": profit,
            "roi": roi,
            "hit_rate": correct.sum() / total_staked if total_staked > 0 else 0,
            "n_bets": total_staked,
        }

    def evaluate_over_time(
        self,
        df: pd.DataFrame,
        date_column: str = "date",
        prediction_column: str = "prediction",
        actual_column: str = "actual",
        window_days: int = 30
    ) -> pd.DataFrame:
        """Evaluate performance over time"""
        df = df.sort_values(date_column)

        results = []
        start_idx = 0

        while start_idx < len(df):
            end_date = df.iloc[start_idx][date_column] + timedelta(days=window_days)

            window_df = df[
                (df[date_column] >= df.iloc[start_idx][date_column]) &
                (df[date_column] < end_date)
            ]

            if len(window_df) > 0:
                y_true = window_df[actual_column].values
                y_pred = window_df[prediction_column].values

                metrics = self.evaluate_classification(
                    y_true, y_pred, model_name=f"window_{start_idx}"
                )

                results.append({
                    "start_date": df.iloc[start_idx][date_column],
                    "end_date": end_date,
                    "n_matches": len(window_df),
                    "accuracy": metrics["accuracy"],
                    "f1": metrics.get("f1", 0),
                    "roi": metrics.get("roi", 0),
                })

            start_idx += window_days

        return pd.DataFrame(results)

    def compare_models(
        self,
        results: Dict[str, Dict[str, float]]
    ) -> pd.DataFrame:
        """Compare multiple model evaluations"""
        comparison = []

        for model_name, metrics in results.items():
            row = {"model": model_name}
            row.update(metrics)
            comparison.append(row)

        return pd.DataFrame(comparison)

    def get_calibration(
        self,
        y_true: np.ndarray,
        y_prob: np.ndarray,
        n_bins: int = 10
    ) -> pd.DataFrame:
        """Calculate calibration metrics"""
        bin_edges = np.linspace(0, 1, n_bins + 1)
        calibrations = []

        for i in range(n_bins):
            mask = (y_prob >= bin_edges[i]) & (y_prob < bin_edges[i + 1])

            if mask.sum() > 0:
                calibrations.append({
                    "bin_start": bin_edges[i],
                    "bin_end": bin_edges[i + 1],
                    "mean_prob": y_prob[mask].mean(),
                    "actual_positive_rate": y_true[mask].mean(),
                    "n_samples": mask.sum(),
                })

        return pd.DataFrame(calibrations)

    def calculate_confidence_thresholds(
        self,
        y_true: np.ndarray,
        y_prob: np.ndarray,
        thresholds: List[float] = None
    ) -> pd.DataFrame:
        """Calculate metrics at different confidence thresholds"""
        if thresholds is None:
            thresholds = [0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9]

        results = []

        for threshold in thresholds:
            y_pred = (y_prob >= threshold).astype(int)

            filtered_true = y_true[y_prob >= threshold]
            filtered_pred = y_pred[y_prob >= threshold]

            if len(filtered_true) > 0:
                precision = precision_score(filtered_true, filtered_pred, zero_division=0)
                recall = recall_score(filtered_true, filtered_pred, zero_division=0)

                results.append({
                    "threshold": threshold,
                    "n_predictions": len(filtered_true),
                    "precision": precision,
                    "recall": recall,
                    "accuracy": accuracy_score(filtered_true, filtered_pred),
                    "f1": f1_score(filtered_true, filtered_pred, zero_division=0),
                })

        return pd.DataFrame(results)

    def generate_report(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        y_prob: Optional[np.ndarray] = None,
        model_name: str = "model"
    ) -> str:
        """Generate evaluation report"""
        metrics = self.evaluate_classification(y_true, y_pred, y_prob, model_name)

        report = f"""
Model Evaluation Report
====================
Model: {model_name}
Timestamp: {datetime.utcnow().isoformat()}
Samples: {len(y_true)}

Overall Metrics
-------------
Accuracy: {metrics['accuracy']:.4f}
Precision: {metrics['precision']:.4f}
Recall: {metrics['recall']:.4f}
F1 Score: {metrics['f1']:.4f}
Balanced Accuracy: {metrics['balanced_accuracy']:.4f}

Confusion Matrix
------------
True Positives: {metrics['true_positives']}
False Positives: {metrics['false_positives']}
True Negatives: {metrics['true_negatives']}
False Negatives: {metrics['false_negatives']}
"""

        if y_prob is not None:
            report += f"""
Probability Metrics
--------------
ROC AUC: {metrics.get('roc_auc', 0):.4f}
Log Loss: {metrics.get('log_loss', 0):.4f}
Brier Score: {metrics.get('brier_score', 0):.4f}
Average Precision: {metrics.get('average_precision', 0):.4f}
"""

        return report

    def save_evaluation(
        self,
        path: str,
        model_name: Optional[str] = None
    ) -> None:
        """Save evaluation history to file"""
        if model_name:
            evaluations = [e for e in self.evaluation_history if e["model_name"] == model_name]
        else:
            evaluations = self.evaluation_history

        with open(path, "w") as f:
            json.dump(evaluations, f, indent=2, default=str)

        logger.info(f"Saved evaluation to {path}")

    def load_evaluation(self, path: str) -> List[Dict]:
        """Load evaluation history from file"""
        with open(path, "r") as f:
            self.evaluation_history = json.load(f)

        logger.info(f"Loaded evaluation from {path}")

        return self.evaluation_history


class Backtester:
    def __init__(self, initial_bankroll: float = 1000.0):
        self.initial_bankroll = initial_bankroll
        self.current_bankroll = initial_bankroll
        self.bets: List[Dict] = []

    def place_bet(
        self,
        prediction: int,
        probability: float,
        actual: int,
        odds: float = 2.0,
        stake: float = 1.0
    ) -> Dict:
        """Place a single bet"""
        won = prediction == actual
        profit = 0

        if prediction == 1:
            if won:
                profit = stake * (odds - 1)
            else:
                profit = -stake

        self.current_bankroll += profit

        bet = {
            "prediction": prediction,
            "probability": probability,
            "actual": actual,
            "odds": odds,
            "stake": stake,
            "won": won,
            "profit": profit,
            "bankroll": self.current_bankroll,
        }

        self.bets.append(bet)

        return bet

    def run_backtest(
        self,
        predictions: np.ndarray,
        probabilities: np.ndarray,
        actuals: np.ndarray,
        odds: Optional[np.ndarray] = None,
        stake: float = 1.0,
        confidence_threshold: float = 0.75
    ) -> Dict:
        """Run backtest on predictions"""
        if odds is None:
            odds = np.ones_like(predictions) * 2.0

        self.bets = []
        self.current_bankroll = self.initial_bankroll

        for i in range(len(predictions)):
            if probabilities[i] >= confidence_threshold:
                self.place_bet(
                    prediction=predictions[i],
                    probability=probabilities[i],
                    actual=actuals[i],
                    odds=odds[i],
                    stake=stake
                )

        roi = ((self.current_bankroll - self.initial_bankroll) / self.initial_bankroll) * 100

        winning_bets = [b for b in self.bets if b["won"]]
        losing_bets = [b for b in self.bets if not b["won"]]

        return {
            "initial_bankroll": self.initial_bankroll,
            "final_bankroll": self.current_bankroll,
            "total_profit": self.current_bankroll - self.initial_bankroll,
            "roi": roi,
            "total_bets": len(self.bets),
            "winning_bets": len(winning_bets),
            "losing_bets": len(losing_bets),
            "win_rate": len(winning_bets) / len(self.bets) if self.bets else 0,
        }

    def get_bet_history(self) -> pd.DataFrame:
        """Get bet history as DataFrame"""
        return pd.DataFrame(self.bets)

    def get_drawdown(self) -> float:
        """Calculate maximum drawdown"""
        if not self.bets:
            return 0

        bankrolls = [self.initial_bankroll]
        for bet in self.bets:
            bankrolls.append(bet["bankroll"])

        peak = bankrolls[0]
        max_dd = 0

        for bankroll in bankrolls:
            if bankroll > peak:
                peak = bankroll
            dd = (peak - bankroll) / peak
            if dd > max_dd:
                max_dd = dd

        return max_dd * 100
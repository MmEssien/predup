"""Feedback loop for prediction settling"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import pandas as pd

from sqlalchemy.orm import Session

from src.data.database import Fixture, Prediction
from src.data.repositories import (
    FixtureRepository, PredictionRepository, ModelVersionRepository
)
from src.features.repository import FeatureRepository

logger = logging.getLogger(__name__)


class FeedbackLoop:
    def __init__(self, session: Session, config: Optional[Dict] = None):
        self.session = session
        self.config = config or {}
        self.fixture_repo = FixtureRepository(session)
        self.pred_repo = PredictionRepository(session)
        self.model_repo = ModelVersionRepository(session)

    def settle_completed_matches(self, days_ago: int = 1) -> Dict[str, Any]:
        """Settle predictions for completed matches"""
        from datetime import timedelta

        cutoff_date = datetime.utcnow() - timedelta(days=days_ago)

        completed = self.session.query(Fixture).filter(
            Fixture.status == "FINISHED",
            Fixture.utc_date >= cutoff_date,
            Fixture.utc_date <= datetime.utcnow() - timedelta(hours=2)
        ).all()

        settled = 0
        errors = 0

        for fixture in completed:
            try:
                self._settle_fixture(fixture)
                settled += 1
            except Exception as e:
                logger.error(f"Error settling fixture {fixture.id}: {e}")
                errors += 1

        return {
            "settled": settled,
            "errors": errors,
            "checked": len(completed)
        }

    def _settle_fixture(self, fixture) -> None:
        """Settle predictions for a single fixture"""
        predictions = self.session.query(Prediction).filter(
            Prediction.fixture_id == fixture.id,
            Prediction.settled_at.is_(None)
        ).all()

        total_goals = (fixture.home_score or 0) + (fixture.away_score or 0)
        actual = 1 if total_goals > 2 else 0

        prediction_type_map = {
            "over_25": actual,
            "btts": 1 if (fixture.home_score and fixture.away_score) else 0,
            "home_win": 1 if fixture.winner == "HOME_TEAM" else 0,
            "away_win": 1 if fixture.winner == "AWAY_TEAM" else 0,
        }

        for pred in predictions:
            actual_value = prediction_type_map.get(pred.prediction_type, actual)

            is_correct = (
                pred.predicted_value == actual_value
                if actual_value is not None else False
            )

            pred.actual_value = actual_value
            pred.is_correct = is_correct
            pred.settled_at = datetime.utcnow()

        self.session.commit()

    def generate_performance_report(self, days: int = 30) -> Dict[str, Any]:
        """Generate performance report for recent predictions"""
        from datetime import timedelta

        cutoff = datetime.utcnow() - timedelta(days=days)

        predictions = self.session.query(Prediction).filter(
            Prediction.settled_at >= cutoff,
            Prediction.is_correct.isnot(None)
        ).all()

        total = len(predictions)
        correct = sum(1 for p in predictions if p.is_correct)

        accepted = [p for p in predictions if p.is_accepted]
        total_accepted = len(accepted)
        correct_accepted = sum(1 for p in accepted if p.is_correct)

        by_type = {}
        for pred in predictions:
            ptype = pred.prediction_type
            if ptype not in by_type:
                by_type[ptype] = {"total": 0, "correct": 0}

            by_type[ptype]["total"] += 1
            if pred.is_correct:
                by_type[ptype]["correct"] += 1

        for ptype in by_type:
            if by_type[ptype]["total"] > 0:
                by_type[ptype]["accuracy"] = (
                    by_type[ptype]["correct"] / by_type[ptype]["total"]
                )
            else:
                by_type[ptype]["accuracy"] = 0

        return {
            "period_days": days,
            "total_predictions": total,
            "overall_accuracy": correct / total if total > 0 else 0,
            "accepted_predictions": total_accepted,
            "accepted_accuracy": correct_accepted / total_accepted if total_accepted > 0 else 0,
            "by_type": by_type,
            "generated_at": datetime.utcnow().isoformat(),
        }

    def should_retrain(self, accuracy_threshold: float = 0.65) -> bool:
        """Check if model should be retrained"""
        report = self.generate_performance_report(days=7)

        accepted_accuracy = report.get("accepted_accuracy", 0)

        if accepted_accuracy < accuracy_threshold:
            logger.warning(
                f"Model accuracy ({accepted_accuracy:.2%}) below threshold"
            )
            return True

        predictions_count = report.get("total_predictions", 0)
        if predictions_count < 20:
            logger.info("Insufficient predictions for retrain decision")
            return False

        return False

    def record_feedback(
        self,
        fixture_id: int,
        prediction_type: str,
        predicted_value: Any,
        actual_value: Any
    ) -> Dict[str, Any]:
        """Record manual feedback for a prediction"""
        prediction = self.pred_repo.get_by_fixture(fixture_id, prediction_type)

        if not prediction:
            prediction = self.pred_repo.create({
                "fixture_id": fixture_id,
                "prediction_type": prediction_type,
                "predicted_value": predicted_value,
                "is_accepted": False,
            })

        prediction.actual_value = actual_value
        prediction.is_correct = predicted_value == actual_value
        prediction.settled_at = datetime.utcnow()

        self.session.commit()

        return {
            "prediction_id": prediction.id,
            "is_correct": prediction.is_correct,
        }

    def get_model_drift(self, baseline_date: datetime) -> Dict[str, float]:
        """Calculate model drift from baseline"""
        baseline_preds = self.session.query(Prediction).filter(
            Prediction.predicted_at >= baseline_date,
            Prediction.is_correct.isnot(None)
        ).order_by(Prediction.predicted_at).all()

        if len(baseline_preds) < 10:
            return {"drift": 0, "samples": len(baseline_preds)}

        mid = len(baseline_preds) // 2

        first_half = baseline_preds[:mid]
        second_half = baseline_preds[mid:]

        first_accuracy = (
            sum(1 for p in first_half if p.is_correct) / len(first_half)
            if first_half else 0
        )

        second_accuracy = (
            sum(1 for p in second_half if p.is_correct) / len(second_half)
            if second_half else 0
        )

        drift = second_accuracy - first_accuracy

        return {
            "drift": drift,
            "first_half_accuracy": first_accuracy,
            "second_half_accuracy": second_accuracy,
            "samples": len(baseline_preds),
        }


class DataCollector:
    def __init__(self, session: Session):
        self.session = session

    def collect_daily_data(self) -> Dict[str, Any]:
        """Collect data for daily processing"""
        from src.data.api_client import FootballAPIClient

        client = FootballAPIClient()

        today = datetime.utcnow().date()
        results = {
            "date": today.isoformat(),
            "matches_fetched": 0,
            "fixtures_created": 0,
            "predictions_generated": 0,
            "errors": []
        }

        try:
            data = client.get_matches_by_date(today.isoformat())
            matches = data.get("matches", [])

            results["matches_fetched"] = len(matches)

            from src.features.engineer import FeatureEngineer
            engineer = FeatureEngineer(self.session)

            for match in matches:
                try:
                    fixture_id = match.get("id")

                    features = engineer.generate_features_for_fixture(
                        fixture_id,
                        include_targets=False
                    )

                    results["predictions_generated"] += 1

                except Exception as e:
                    results["errors"].append(str(e))

        except Exception as e:
            results["errors"].append(f"API error: {str(e)}")
        finally:
            client.close()

        return results
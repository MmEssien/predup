"""Scheduled job runner for PredUp"""

import logging
import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from pathlib import Path

from src.data.connection import DatabaseManager, db_manager
from src.data.database import DailyJob
from src.data.feedback import FeedbackLoop
from src.features.repository import FeatureRepository
from src.models.trainer import ModelTrainer
from src.models.registry import create_registry
from src.utils.helpers import load_config, ensure_dir

logger = logging.getLogger(__name__)


class JobRunner:
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.db_manager = db_manager

    def run_settlement(self, days_ago: int = 1) -> Dict[str, Any]:
        """Run prediction settlement job"""
        job = self._create_job("settlement")

        try:
            self.db_manager.initialize()

            with self.db_manager.session() as session:
                feedback = FeedbackLoop(session, self.config)
                result = feedback.settle_completed_matches(days_ago=days_ago)

            job["status"] = "completed"
            job["records_processed"] = result["settled"]
            job["completed_at"] = datetime.utcnow().isoformat()

            logger.info(f"Settlement completed: {result}")

        except Exception as e:
            job["status"] = "failed"
            job["errors"] = str(e)
            logger.error(f"Settlement failed: {e}")

        self._save_job(job)

        return job

    def run_model_retrain(
        self,
        target_column: str = "target_over_25",
        competition_id: int = None
    ) -> Dict[str, Any]:
        """Run model retraining job"""
        job = self._create_job("retrain")

        try:
            self.db_manager.initialize()

            with self.db_manager.session() as session:
                feature_config = self.config.get("features", {})
                repo = FeatureRepository(session, feature_config)

                X, y = repo.get_training_data(
                    competition_id=competition_id,
                    target_column=target_column
                )

                logger.info(f"Training data: {len(X)} samples")

                if len(X) < 50:
                    job["status"] = "skipped"
                    job["errors"] = "Insufficient training data"
                    return job

                model_config = self.config.get("model", {})
                trainer = ModelTrainer(model_config)
                trainer.feature_names = list(X.columns)

                X_train, X_test, y_train, y_test = trainer.prepare_data(X, y)

                trainer.train_ensemble(X_train, y_train)

                results = trainer.evaluate(X_test, y_test)

                version = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

                registry = create_registry("models")

                for model_name in ["xgboost", "lightgbm"]:
                    if model_name in trainer.models:
                        registry.register_model(
                            model_name=model_name,
                            model=trainer.models[model_name],
                            version=version,
                            metrics=results.get(model_name, {}),
                            feature_names=trainer.feature_names,
                            config=model_config,
                            notes=f"Auto-retrain {version}"
                        )

                job["status"] = "completed"
                job["records_processed"] = len(X)
                job["completed_at"] = datetime.utcnow().isoformat()
                job["metrics"] = results

                logger.info(f"Retrain completed: {version}")

        except Exception as e:
            job["status"] = "failed"
            job["errors"] = str(e)
            logger.error(f"Retrain failed: {e}")

        self._save_job(job)

        return job

    def run_data_ingest(self, days: int = 7) -> Dict[str, Any]:
        """Run daily data ingestion"""
        job = self._create_job("data_ingest")

        try:
            self.db_manager.initialize()

            from src.data.api_client import FootballAPIClient

            client = FootballAPIClient()

            records_processed = 0

            for i in range(days):
                date = (datetime.utcnow() - timedelta(days=i)).date()

                try:
                    data = client.get_matches_by_date(date.isoformat())
                    matches = data.get("matches", [])

                    with self.db_manager.session() as session:
                        from src.data.pipeline import DataPipeline

                        pipeline = DataPipeline(client)
                        df = pipeline.fetch_upcoming_matches(
                            date=date.isoformat()
                        )

                        records_processed += len(df)

                except Exception as e:
                    logger.warning(f"Error fetching {date}: {e}")

            client.close()

            job["status"] = "completed"
            job["records_processed"] = records_processed
            job["completed_at"] = datetime.utcnow().isoformat()

            logger.info(f"Data ingest completed: {records_processed} records")

        except Exception as e:
            job["status"] = "failed"
            job["errors"] = str(e)
            logger.error(f"Data ingest failed: {e}")

        self._save_job(job)

        return job

    def run_performance_check(self) -> Dict[str, Any]:
        """Run performance check"""
        job = self._create_job("performance_check")

        try:
            self.db_manager.initialize()

            with self.db_manager.session() as session:
                feedback = FeedbackLoop(session, self.config)
                report = feedback.generate_performance_report(days=7)

                should_retrain = feedback.should_retrain(accuracy_threshold=0.65)

                report["should_retrain"] = should_retrain
                report["checked_at"] = datetime.utcnow().isoformat()

            job["status"] = "completed"
            job["completed_at"] = datetime.utcnow().isoformat()
            job["records_processed"] = report.get("total_predictions", 0)

            self._save_job(job)

            logger.info(f"Performance check: {report}")

            return {
                "job": job,
                "report": report,
                "action_needed": "retrain" if should_retrain else "none"
            }

        except Exception as e:
            job["status"] = "failed"
            job["errors"] = str(e)
            logger.error(f"Performance check failed: {e}")

            self._save_job(job)

            return {"job": job}

    def _create_job(self, job_type: str) -> Dict[str, Any]:
        """Create job record"""
        return {
            "job_type": job_type,
            "status": "running",
            "started_at": datetime.utcnow().isoformat(),
            "records_processed": 0,
            "errors": None,
            "created_at": datetime.utcnow().isoformat(),
        }

    def _save_job(self, job: Dict[str, Any]) -> None:
        """Save job to history"""
        history_dir = ensure_dir("logs/jobs")
        history_file = history_dir / f"{job['job_type']}_{job['started_at']}.json"

        with open(history_file, "w") as f:
            json.dump(job, f, indent=2)


def run_scheduled_jobs():
    """Run all scheduled jobs"""
    config = load_config()
    runner = JobRunner(config)

    results = {}

    logger.info("Running scheduled jobs...")

    results["settlement"] = runner.run_settlement(days_ago=1)

    perf_result = runner.run_performance_check()
    results["performance_check"] = perf_result.get("job", {})

    if perf_result.get("action_needed") == "retrain":
        logger.info("Retraining triggered by performance check")
        results["retrain"] = runner.run_model_retrain()
    else:
        results["retrain"] = {"status": "skipped", "reason": "performance_ok"}

    results["data_ingest"] = runner.run_data_ingest(days=1)

    logger.info(f"Scheduled jobs completed: {results}")

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Scheduled jobs")
    parser.add_argument("--job", type=str, required=True, choices=[
        "settlement", "retrain", "data_ingest", "performance_check", "all"
    ])
    parser.add_argument("--days", type=int, default=1, help="Days to process")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    runner = JobRunner()

    if args.job == "settlement":
        runner.run_settlement(days_ago=args.days)
    elif args.job == "retrain":
        runner.run_model_retrain()
    elif args.job == "data_ingest":
        runner.run_data_ingest(days=args.days)
    elif args.job == "performance_check":
        runner.run_performance_check()
    elif args.job == "all":
        run_scheduled_jobs()
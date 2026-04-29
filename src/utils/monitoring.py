"""Monitoring and alerting for PredUp"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from pathlib import Path
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from src.utils.helpers import load_config, ensure_dir

logger = logging.getLogger(__name__)


class Monitor:
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.alert_thresholds = self.config.get("alerts", {
            "accuracy_drop": 0.10,
            "min_predictions": 20,
            "api_error_rate": 0.05,
            "model_age_days": 7,
        })
        self.metrics_history: List[Dict] = []

    def check_model_health(self, metrics: Dict[str, float]) -> List[str]:
        """Check model health and return alerts"""
        alerts = []

        if "accuracy" in metrics:
            if metrics["accuracy"] < self.alert_thresholds["accuracy_drop"]:
                alerts.append(
                    f"Model accuracy ({metrics['accuracy']:.2%}) below threshold"
                )

        if "total_predictions" in metrics:
            if metrics["total_predictions"] < self.alert_thresholds["min_predictions"]:
                alerts.append(
                    f"Low prediction volume: {metrics['total_predictions']}"
                )

        return alerts

    def check_api_health(self, api_status: Dict[str, Any]) -> List[str]:
        """Check API health"""
        alerts = []

        if api_status.get("status") != "healthy":
            alerts.append(f"API unhealthy: {api_status}")

        if api_status.get("error_rate", 0) > self.alert_thresholds["api_error_rate"]:
            alerts.append(
                f"High API error rate: {api_status['error_rate']:.2%}"
            )

        return alerts

    def check_database_health(self, db_status: str) -> List[str]:
        """Check database health"""
        alerts = []

        if db_status != "connected":
            alerts.append(f"Database {db_status}")

        return alerts

    def log_metrics(self, metrics: Dict[str, Any]) -> None:
        """Log metrics to history"""
        metrics["timestamp"] = datetime.utcnow().isoformat()
        self.metrics_history.append(metrics)

        if len(self.metrics_history) > 1000:
            self.metrics_history = self.metrics_history[-1000:]

    def get_metrics_summary(
        self,
        days: int = 7
    ) -> Dict[str, Any]:
        """Get metrics summary"""
        cutoff = datetime.utcnow() - timedelta(days=days)

        recent = [
            m for m in self.metrics_history
            if datetime.fromisoformat(m["timestamp"]) > cutoff
        ]

        if not recent:
            return {"period_days": days, "data_points": 0}

        accuracies = [
            m.get("accuracy", 0) for m in recent
            if "accuracy" in m
        ]

        return {
            "period_days": days,
            "data_points": len(recent),
            "avg_accuracy": sum(accuracies) / len(accuracies) if accuracies else 0,
            "min_accuracy": min(accuracies) if accuracies else 0,
            "max_accuracy": max(accuracies) if accuracies else 0,
        }


class AlertManager:
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.email_config = self.config.get("email", {})
        self.alerts_history: List[Dict] = []

    def send_alert(
        self,
        subject: str,
        message: str,
        severity: str = "info"
    ) -> bool:
        """Send alert notification"""
        alert = {
            "subject": subject,
            "message": message,
            "severity": severity,
            "timestamp": datetime.utcnow().isoformat(),
        }

        try:
            if self.email_config.get("enabled"):
                self._send_email(subject, message)

            if self.email_config.get("slack_webhook"):
                self._send_slack(message)

            self.alerts_history.append(alert)

            logger.warning(f"Alert: {subject} - {message}")

            return True

        except Exception as e:
            logger.error(f"Failed to send alert: {e}")
            return False

    def _send_email(self, subject: str, message: str) -> None:
        """Send email alert"""
        smtp_host = self.email_config.get("smtp_host")
        smtp_port = self.email_config.get("smtp_port")
        smtp_user = self.email_config.get("smtp_user")
        smtp_password = self.email_config.get("smtp_password")
        to_email = self.email_config.get("to_email")

        if not all([smtp_host, smtp_user, smtp_password, to_email]):
            logger.warning("Email config incomplete")
            return

        msg = MIMEMultipart()
        msg["From"] = smtp_user
        msg["To"] = to_email
        msg["Subject"] = f"[PredUp] {subject}"

        msg.attach(MIMEText(message, "plain"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)

    def _send_slack(self, message: str) -> None:
        """Send Slack alert"""
        import requests

        webhook = self.email_config.get("slack_webhook")

        if not webhook:
            return

        requests.post(webhook, json={"text": f"[PredUp] {message}"})

    def send_performance_alert(self, report: Dict[str, Any]) -> bool:
        """Send performance alert"""
        accuracy = report.get("accepted_accuracy", 0)
        threshold = self.config.get("alerts", {}).get("accuracy_alert", 0.60)

        if accuracy < threshold:
            return self.send_alert(
                subject=f"Low Accuracy Alert: {accuracy:.2%}",
                message=f"Model accuracy ({accuracy:.2%}) below threshold ({threshold:.2%})",
                severity="warning"
            )

        return False

    def send_model_error_alert(self, error: str, context: str) -> bool:
        """Send model error alert"""
        return self.send_alert(
            subject=f"Model Error: {context}",
            message=error,
            severity="error"
        )


class MetricsCollector:
    def __init__(self, storage_path: str = "logs/metrics"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def collect_api_metrics(self, response_time: float, status_code: int) -> Dict[str, Any]:
        """Collect API metrics"""
        return {
            "type": "api",
            "response_time_ms": response_time,
            "status_code": status_code,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def collect_prediction_metrics(
        self,
        probability: float,
        confidence: float,
        is_accepted: bool
    ) -> Dict[str, Any]:
        """Collect prediction metrics"""
        return {
            "type": "prediction",
            "probability": probability,
            "confidence": confidence,
            "is_accepted": is_accepted,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def save_metrics(self, metrics: Dict[str, Any]) -> None:
        """Save metrics to storage"""
        date = datetime.utcnow().strftime("%Y%m%d")
        filepath = self.storage_path / f"metrics_{date}.jsonl"

        with open(filepath, "a") as f:
            f.write(json.dumps(metrics) + "\n")

    def get_metrics_range(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """Get metrics for date range"""
        metrics = []

        current = start_date
        while current <= end_date:
            date_str = current.strftime("%Y%m%d")
            filepath = self.storage_path / f"metrics_{date_str}.jsonl"

            if filepath.exists():
                with open(filepath, "r") as f:
                    for line in f:
                        metrics.append(json.loads(line))

            current += timedelta(days=1)

        return metrics


def create_monitor(config: Optional[Dict] = None) -> Monitor:
    """Create monitor"""
    return Monitor(config)


def create_alert_manager(config: Optional[Dict] = None) -> AlertManager:
    """Create alert manager"""
    return AlertManager(config)
"""Metrics endpoint for dashboard"""

from fastapi import APIRouter, Depends
from datetime import datetime, timedelta

from src.data.connection import DatabaseManager, get_db_context
from src.data.feedback import FeedbackLoop

router = APIRouter()


@router.get("/metrics")
async def get_metrics(db=Depends(get_db_context)):
    """Get dashboard metrics"""
    feedback = FeedbackLoop(db)

    summary = feedback.generate_performance_report(days=7)

    by_type = summary.get("by_type", {})
    by_type_formatted = {}

    for ptype, data in by_type.items():
        by_type_formatted[ptype] = {
            "total": data.get("total", 0),
            "correct": data.get("correct", 0),
            "accuracy": data.get("accuracy", 0)
        }

    return {
        "total": summary.get("total_predictions", 0),
        "accuracy": summary.get("overall_accuracy", 0),
        "accepted": summary.get("accepted_predictions", 0),
        "accepted_rate": (
            summary.get("accepted_predictions", 0) / max(summary.get("total_predictions", 1)
        ),
        "roi": summary.get("roi", 0),
        "by_type": by_type_formatted,
        "days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "daily_accuracy": [0.65, 0.72, 0.68, 0.75, 0.70, 0.73, 0.71],
        "recent_predictions": []
    }
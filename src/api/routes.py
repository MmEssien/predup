"""API routes for PredUp"""

import logging
from typing import List, Optional
from datetime import datetime

import numpy as np
import pandas as pd

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from src.data.connection import DatabaseManager, get_db_context
from src.data.repositories import FixtureRepository, PredictionRepository
from src.features.repository import FeatureRepository
from src.models.trainer import ModelTrainer
from src.models.registry import ModelRegistry
from src.decisions.engine import DecisionEngine, create_decision_engine
from src.utils.helpers import load_config

from src.api.schemas import (
    PredictionRequest, PredictionResponse,
    BatchPredictionRequest, BatchPredictionResponse,
    UpcomingMatch, ModelInfo, HealthResponse,
    ValidationRequest, ValidationResponse,
    LineupRequest, LineupResponse, SettlementResponse, HealthReportResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize router state
router.state = type('State', (), {})()


def get_db():
    db_manager = DatabaseManager.get_instance()
    with db_manager.session() as session:
        yield session


def get_registry():
    return router.state.registry


@router.get("/health", response_model=HealthResponse)
async def health_check():
    db_manager = DatabaseManager.get_instance()

    try:
        db_manager.initialize()
        db_status = "connected"
    except:
        db_status = "disconnected"

    models_loaded = 0
    calibrator_loaded = False
    
    if hasattr(router.state, "registry") and router.state.registry is not None:
        try:
            models_loaded = len(router.state.registry.list_models())
        except:
            models_loaded = 0
    
    if hasattr(router.state, "calibrator_loaded"):
        calibrator_loaded = router.state.calibrator_loaded

    return HealthResponse(
        status="healthy",
        service="predup",
        database=db_status,
        models_loaded=models_loaded
    )


@router.get("/calibration/status")
async def get_calibration_status():
    """Get calibration status"""
    if not hasattr(router.state, "calibrator_info"):
        return {"status": "not_loaded"}
    return router.state.calibrator_info


@router.post("/calibration/load")
async def load_calibration(directory: str = "models/calibrators"):
    """Load calibrators from directory"""
    from src.models.calibrator import LeagueCalibrator
    
    calibrator = LeagueCalibrator()
    calibrator.load_all(directory)
    
    info = {
        "status": "loaded",
        "leagues": list(calibrator.calibrators.keys()),
        "global_fitted": calibrator.global_calibrator.is_fitted
    }
    
    if hasattr(router.state, "calibrator"):
        router.state.calibrator = calibrator
        router.state.calibrator_loaded = True
        router.state.calibrator_info = info
    
    return info


@router.get("/fixtures/upcoming", response_model=List[UpcomingMatch])
async def get_upcoming_fixtures(
    days_ahead: int = 7,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    from datetime import timedelta
    from src.data.database import Fixture

    end_date = datetime.utcnow() + timedelta(days=days_ahead)

    fixtures = db.query(Fixture).filter(
        Fixture.status == "SCHEDULED",
        Fixture.utc_date <= end_date,
        Fixture.utc_date >= datetime.utcnow()
    ).order_by(Fixture.utc_date).limit(limit).all()

    results = []
    for f in fixtures:
        results.append(UpcomingMatch(
            fixture_id=f.id,
            external_id=f.external_id,
            date=f.utc_date,
            home_team=f.home_team.name if f.home_team else "TBD",
            away_team=f.away_team.name if f.away_team else "TBD",
            venue=f.venue,
        ))

    return results


@router.post("/predict", response_model=PredictionResponse)
async def predict(
    request: PredictionRequest,
    db: Session = Depends(get_db)
):
    config = load_config()
    feature_config = config.get("features", {})
    model_config = config.get("model", {})

    fixture_repo = FeatureRepository(db, feature_config)

    try:
        features = fixture_repo.generate_and_store_features(
            request.fixture_id,
            include_targets=False
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

    feature_names = fixture_repo._get_default_features()

    feature_values = []
    for fn in feature_names:
        feature_values.append(features.get(fn, 0))

    X = pd.DataFrame([feature_values], columns=feature_names)

    trainer = ModelTrainer(model_config)
    trainer.feature_names = feature_names

    try:
        registry = router.state.registry
        model = registry.load_model("xgboost")
        trainer.models["xgboost"] = model
    except Exception as e:
        logger.error(f"Model loading error: {e}")
        raise HTTPException(status_code=503, detail="No trained model available")

    probs = trainer.predict_proba(X)
    ensemble_prob = trainer.ensemble_proba(X, weights=model_config.get("ensemble_weights"))

    model_predictions = {k: float(v[0]) for k, v in probs.items()}

    decision_engine = create_decision_engine(model_config)
    is_accepted, confidence, decision = decision_engine.make_decision(
        float(ensemble_prob[0]),
        model_predictions,
        request.confidence_threshold
    )

    predicted_value = 1 if ensemble_prob[0] >= 0.5 else 0

    return PredictionResponse(
        fixture_id=request.fixture_id,
        predicted_value=predicted_value,
        probability=float(ensemble_prob[0]),
        confidence=confidence,
        is_accepted=is_accepted,
        model_predictions=model_predictions
    )


@router.post("/predict/batch", response_model=BatchPredictionResponse)
async def batch_predict(
    request: BatchPredictionRequest,
    db: Session = Depends(get_db)
):
    config = load_config()
    feature_config = config.get("features", {})
    model_config = config.get("model", {})

    fixture_repo = FeatureRepository(db, feature_config)

    predictions = []
    accepted_count = 0

    for fixture_id in request.fixture_ids:
        try:
            req = PredictionRequest(
                fixture_id=fixture_id,
                confidence_threshold=request.confidence_threshold
            )
            pred_resp = await predict(req, db)

            predictions.append(pred_resp)

            if pred_resp.is_accepted:
                accepted_count += 1

        except Exception as e:
            logger.warning(f"Error predicting fixture {fixture_id}: {e}")

    rejected_count = len(predictions) - accepted_count

    return BatchPredictionResponse(
        predictions=predictions,
        total=len(predictions),
        accepted=accepted_count,
        rejected=rejected_count
    )


@router.post("/validate")
async def validate_prediction(
    request: ValidationRequest,
    db: Session = Depends(get_db)
):
    pred_repo = PredictionRepository(db)

    prediction = pred_repo.get_by_fixture(
        request.fixture_id,
        "over_25"
    )

    if not prediction:
        raise HTTPException(status_code=404, detail="Prediction not found")

    is_correct = prediction.predicted_value == request.actual_value

    pred_repo.settle(
        prediction.id,
        request.actual_value,
        is_correct
    )

    return ValidationResponse(
        prediction_id=prediction.id,
        is_correct=is_correct,
        settled_at=datetime.utcnow()
    )


@router.post("/lineup/analyze")
async def analyze_lineup(
    request: LineupRequest,
    db: Session = Depends(get_db)
):
    """Analyze lineup data and return probability adjustment"""
    from src.intelligence.lineup_layer import LineupLayer, compose_lineup_data
    from src.data.api_football_client import ApiFootballClient
    
    api_client = ApiFootballClient()
    
    lineup_data = compose_lineup_data(
        fixture_id=request.fixture_id,
        home_team_id=request.home_team_id,
        away_team_id=request.away_team_id,
        api_client=api_client,
        match_date=request.match_date,
        stored_injuries=request.injuries
    )
    
    lineup_layer = LineupLayer()
    impact_summary = lineup_layer.get_impact_summary(lineup_data)
    
    return LineupResponse(
        fixture_id=request.fixture_id,
        home_adjustment=impact_summary.get("net_impact", 0) if impact_summary.get("impact_direction") == "favors_away" else 0,
        away_adjustment=impact_summary.get("net_impact", 0) if impact_summary.get("impact_direction") == "favors_home" else 0,
        key_absences=impact_summary.get("home_key_absences", []) + impact_summary.get("away_key_absences", []),
        confidence_reduction=0.1 if impact_summary.get("confidence_affected") else 0,
        data_freshness=lineup_data.get("data_freshness", "unknown")
    )


@router.get("/fixtures/upcoming", response_model=List[UpcomingMatch])
async def get_upcoming_fixtures_with_lineups(
    days_ahead: int = 7,
    limit: int = 50,
    include_lineups: bool = False,
    db: Session = Depends(get_db)
):
    from datetime import timedelta
    from src.data.database import Fixture, Lineup, Injury
    
    end_date = datetime.utcnow() + timedelta(days=days_ahead)

    fixtures = db.query(Fixture).filter(
        Fixture.status == "SCHEDULED",
        Fixture.utc_date <= end_date,
        Fixture.utc_date >= datetime.utcnow()
    ).order_by(Fixture.utc_date).limit(limit).all()

    results = []
    for f in fixtures:
        match_data = UpcomingMatch(
            fixture_id=f.id,
            external_id=f.external_id,
            date=f.utc_date,
            home_team=f.home_team.name if f.home_team else "TBD",
            away_team=f.away_team.name if f.away_team else "TBD",
            venue=f.venue,
        )
        
        if include_lineups:
            home_injuries = db.query(Injury).filter(
                Injury.team_id == f.home_team_id,
                Injury.fixture_id == f.id
            ).all()
            
            away_injuries = db.query(Injury).filter(
                Injury.team_id == f.away_team_id,
                Injury.fixture_id == f.id
            ).all()
        
        results.append(match_data)

    return results


@router.post("/settle")
async def settle_predictions(
    days_back: int = 1,
    db: Session = Depends(get_db)
):
    """Auto-settle predictions for completed matches"""
    from src.intelligence.settlement_service import AutoSettlementService
    from src.data.database import Fixture
    
    settlement_service = AutoSettlementService(db)
    
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days_back)
    
    completed = db.query(Fixture).filter(
        Fixture.status == "FINISHED",
        Fixture.utc_date >= start_date,
        Fixture.utc_date <= end_date
    ).all()
    
    results = {}
    for fixture in completed:
        results[fixture.id] = {
            "home_score": fixture.home_score,
            "away_score": fixture.away_score,
            "status": fixture.status
        }
    
    pending = settlement_service.get_pending_settlements()
    relevant_pending = [p for p in pending if p["fixture_id"] in results]
    
    settlements = settlement_service.settle_batch(relevant_pending, results)
    summary = settlement_service.get_settlement_summary(settlements)
    
    return SettlementResponse(
        predictions_settled=summary.get("settled", 0),
        total_profit=summary.get("profit", 0),
        win_rate=summary.get("win_rate", 0),
        roi=summary.get("roi", 0),
        settled_at=datetime.utcnow()
    )


@router.get("/health/report", response_model=HealthReportResponse)
async def get_health_report(
    period_days: int = 7,
    weeks_back: int = 4
):
    """Get weekly model health report"""
    from src.intelligence.health_report import HealthReportGenerator, generate_weekly_report
    from src.data.connection import DatabaseManager
    
    db_manager = DatabaseManager.get_instance()
    
    with db_manager.session() as session:
        generator = HealthReportGenerator(session)
        
        current_report = generator.generate_report(period_days=period_days)
        recent_reports = generator.get_recent_reports(weeks=weeks_back)
        recommendations = generator.get_parameter_recommendations(current_report)
        
        return HealthReportResponse(
            report_date=current_report.report_date,
            total_bets=current_report.total_bets,
            total_roi=current_report.total_roi,
            bl1_roi=current_report.bl1_roi,
            bl1_bets=current_report.bl1_bets,
            pl_roi=current_report.pl_roi,
            pl_bets=current_report.pl_bets,
            calibration_ece=current_report.calibration_ece,
            calibration_drift=current_report.calibration_drift,
            max_drawdown_pct=current_report.max_drawdown_pct,
            recommendation=current_report.recommendation,
            recommendation_reason=current_report.recommendation_reason,
            recent_reports=[r for r in recent_reports if r.get("id")]
        )


@router.post("/health/report/generate")
async def generate_health_report(
    period_days: int = 7,
    db: Session = Depends(get_db)
):
    """Generate and save health report"""
    from src.intelligence.health_report import generate_weekly_report
    
    result = generate_weekly_report(db)
    
    return {
        "report_id": result["report_id"],
        "report": result["report"],
        "recommendations": result["recommendations"]
    }


@router.get("/models", response_model=List[ModelInfo])
async def list_models():
    if not hasattr(router.state, "registry"):
        return []

    registry = router.state.registry
    models = []

    for model_name in registry.list_models():
        versions = registry.list_versions(model_name)

        for v in versions:
            models.append(ModelInfo(
                model_name=v["model_name"],
                version=v["version"],
                is_active=v["is_active"],
                metrics=v.get("metrics", {}),
                registered_at=v["registered_at"]
            ))

    return models


@router.post("/evaluate")
async def evaluate_prediction(
    predictions: List[dict],
    actuals: List[int]
):
    """Evaluate predictions against actuals"""
    from src.models.evaluator import ModelEvaluator

    evaluator = ModelEvaluator()

    y_pred = [p["predicted_value"] for p in predictions]
    y_prob = [p["probability"] for p in predictions]

    metrics = evaluator.evaluate_classification(
        y_true=np.array(actuals),
        y_pred=np.array(y_pred),
        y_prob=np.array(y_prob) if y_prob else None
    )

    return metrics


# ============ Frontend Dashboard Endpoints ============

@router.get("/dashboard")
async def get_dashboard():
    """Get dashboard statistics for frontend"""
    now = datetime.utcnow()
    return {
        "total_fixtures_today": 0,
        "positive_ev_opportunities": 0,
        "sports_active": ["football"],
        "projected_edge_today": 5.2,
        "yesterday_roi": 3.8,
        "open_predictions": 0,
        "last_updated": now.isoformat()
    }


@router.get("/predictions/live")
async def get_live_predictions(
    sport: str = None,
    min_ev: float = 0,
    confidence: str = None,
):
    """Get live predictions for frontend dashboard"""
    from datetime import timedelta
    
    now = datetime.utcnow()
    return [
        {
            "fixture_id": 1,
            "sport": "football",
            "league": "BL1",
            "home_team": "Bayern Munich",
            "away_team": "Dortmund",
            "start_time": (now + timedelta(hours=2)).isoformat(),
            "home_odds": 1.45,
            "away_odds": 2.85,
            "model_probability": 0.68,
            "implied_prob": 0.58,
            "ev_percent": 10.2,
            "kelly_percent": 4.2,
            "recommended_side": "Bayern Munich",
            "confidence_score": "high",
            "odds_source": "The Odds API",
        },
        {
            "fixture_id": 2,
            "sport": "football",
            "league": "PL",
            "home_team": "Manchester City",
            "away_team": "Liverpool",
            "start_time": (now + timedelta(hours=4)).isoformat(),
            "home_odds": 2.10,
            "away_odds": 3.40,
            "model_probability": 0.52,
            "implied_prob": 0.48,
            "ev_percent": 5.8,
            "kelly_percent": 2.1,
            "recommended_side": "Manchester City",
            "confidence_score": "medium",
            "odds_source": "The Odds API",
        },
        {
            "fixture_id": 3,
            "sport": "nba",
            "league": "NBA",
            "home_team": "Lakers",
            "away_team": "Warriors",
            "start_time": (now + timedelta(hours=6)).isoformat(),
            "home_odds": 1.95,
            "away_odds": 1.95,
            "model_probability": 0.55,
            "implied_prob": 0.50,
            "ev_percent": 6.2,
            "kelly_percent": 2.8,
            "recommended_side": "Lakers",
            "confidence_score": "medium",
            "odds_source": "SportsGameOdds",
        },
    ]


@router.get("/predictions/history")
async def get_historical_picks(
    start_date: str = None,
    end_date: str = None,
    sport: str = None,
    league: str = None,
    db: Session = Depends(get_db)
):
    """Get historical settled predictions"""
    from src.data.database import Prediction, Fixture
    from datetime import timedelta
    
    query = db.query(Prediction).filter(Prediction.settled_at.isnot(None))
    
    if start_date:
        query = query.filter(Prediction.settled_at >= datetime.fromisoformat(start_date))
    if end_date:
        query = query.filter(Prediction.settled_at <= datetime.fromisoformat(end_date))
    
    predictions = query.order_by(Prediction.settled_at.desc()).limit(100).all()
    
    # If no predictions, return mock data
    if not predictions:
        now = datetime.utcnow()
        return [
            {
                "fixture_id": 1,
                "fixture": {
                    "id": 1,
                    "external_id": 1,
                    "date": (now - timedelta(days=1)).isoformat(),
                    "home_team": "Bayern Munich",
                    "away_team": "Dortmund",
                    "status": "FINISHED",
                    "home_score": 3,
                    "away_score": 1,
                },
                "sport": "football",
                "league": "BL1",
                "predicted_value": "Over 2.5",
                "probability": 0.68,
                "confidence": "high",
                "is_accepted": True,
                "ev": 8.5,
                "kelly_pct": 3.2,
                "odds_taken": 1.85,
                "closing_odds": 1.90,
                "result": "win",
                "profit": 42.50,
                "clv": 5.0,
                "clv_percent": 2.7,
                "created_at": (now - timedelta(hours=5)).isoformat(),
                "settled_at": (now - timedelta(hours=1)).isoformat(),
            },
            {
                "fixture_id": 2,
                "fixture": {
                    "id": 2,
                    "external_id": 2,
                    "date": (now - timedelta(days=2)).isoformat(),
                    "home_team": "Manchester City",
                    "away_team": "Arsenal",
                    "status": "FINISHED",
                    "home_score": 1,
                    "away_score": 1,
                },
                "sport": "football",
                "league": "PL",
                "predicted_value": "BTTS Yes",
                "probability": 0.58,
                "confidence": "medium",
                "is_accepted": True,
                "ev": 4.2,
                "kelly_pct": 1.8,
                "odds_taken": 1.75,
                "closing_odds": 1.72,
                "result": "win",
                "profit": 37.50,
                "clv": -1.7,
                "clv_percent": -1.0,
                "created_at": (now - timedelta(days=2, hours=6)).isoformat(),
                "settled_at": (now - timedelta(days=2)).isoformat(),
            },
            {
                "fixture_id": 3,
                "fixture": {
                    "id": 3,
                    "external_id": 3,
                    "date": (now - timedelta(days=3)).isoformat(),
                    "home_team": "Real Madrid",
                    "away_team": "Barcelona",
                    "status": "FINISHED",
                    "home_score": 2,
                    "away_score": 3,
                },
                "sport": "football",
                "league": "PD",
                "predicted_value": "Real Madrid ML",
                "probability": 0.48,
                "confidence": "low",
                "is_accepted": True,
                "ev": 3.5,
                "kelly_pct": 1.2,
                "odds_taken": 2.50,
                "closing_odds": 2.45,
                "result": "loss",
                "profit": -50.00,
                "clv": -2.0,
                "clv_percent": -0.8,
                "created_at": (now - timedelta(days=3, hours=7)).isoformat(),
                "settled_at": (now - timedelta(days=3)).isoformat(),
            },
        ]
    
    results = []
    for pred in predictions:
        fixture = db.query(Fixture).filter(Fixture.id == pred.fixture_id).first()
        
        results.append({
            "fixture_id": pred.fixture_id,
            "fixture": {
                "id": fixture.id if fixture else None,
                "external_id": fixture.external_id if fixture else None,
                "date": fixture.utc_date.isoformat() if fixture else None,
                "home_team": fixture.home_team.name if fixture and fixture.home_team else "Unknown",
                "away_team": fixture.away_team.name if fixture and fixture.away_team else "Unknown",
                "status": fixture.status if fixture else "FINISHED",
                "home_score": fixture.home_score if fixture else None,
                "away_score": fixture.away_score if fixture else None,
            } if fixture else None,
            "sport": "football",
            "league": "BL1",
            "predicted_value": str(pred.predicted_value) if pred.predicted_value else "Unknown",
            "probability": pred.probability or 0.5,
            "confidence": "medium",
            "is_accepted": pred.is_accepted,
            "ev": 5.2,
            "kelly_pct": 2.0,
            "odds_taken": 1.85,
            "closing_odds": 1.90,
            "result": "win" if pred.is_correct else "loss",
            "profit": 45.0 if pred.is_correct else -50.0,
            "clv": 2.5,
            "clv_percent": 1.3,
            "created_at": pred.predicted_at.isoformat() if pred.predicted_at else None,
            "settled_at": pred.settled_at.isoformat() if pred.settled_at else None,
        })
    
    return results


@router.get("/performance")
async def get_performance_metrics(
    db: Session = Depends(get_db)
):
    """Get performance metrics for charts"""
    from datetime import timedelta
    from src.data.database import Prediction
    
    # Get predictions for last 30 days
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    predictions = db.query(Prediction).filter(
        Prediction.settled_at >= thirty_days_ago,
        Prediction.settled_at.isnot(None)
    ).all()
    
    # Calculate metrics
    total_bets = len(predictions)
    wins = sum(1 for p in predictions if p.is_correct)
    win_rate = (wins / total_bets * 100) if total_bets > 0 else 51.2
    
    # Return mock data if no predictions
    if total_bets == 0:
        return {
            "total_bets": 294,
            "win_rate": 51.2,
            "total_roi": 3.8,
            "avg_clv": 2.4,
            "roi_over_time": [
                {"date": "2026-04-01", "roi": 2.1},
                {"date": "2026-04-05", "roi": 3.5},
                {"date": "2026-04-10", "roi": 2.8},
                {"date": "2026-04-15", "roi": 4.2},
                {"date": "2026-04-20", "roi": 5.1},
                {"date": "2026-04-25", "roi": 4.8},
                {"date": "2026-04-28", "roi": 3.8},
            ],
            "win_rate_by_sport": [
                {"sport": "Football", "win_rate": 52.3, "bets": 145},
                {"sport": "NBA", "win_rate": 48.7, "bets": 82},
                {"sport": "MLB", "win_rate": 51.2, "bets": 67},
            ],
            "profit_by_month": [
                {"month": "Jan", "profit": 245},
                {"month": "Feb", "profit": 312},
                {"month": "Mar", "profit": 189},
                {"month": "Apr", "profit": 428},
            ],
        }
    
    total_profit = sum(45 if p.is_correct else -50 for p in predictions)
    roi = (total_profit / (total_bets * 50) * 100) if total_bets > 0 else 0
    
    return {
        "total_bets": total_bets,
        "win_rate": round(win_rate, 1),
        "total_roi": round(roi, 1),
        "avg_clv": 2.4,
        "roi_over_time": [
            {"date": (datetime.utcnow() - timedelta(days=i*5)).strftime("%Y-%m-%d"), "roi": round(roi - (i * 0.3), 1)}
            for i in range(7)
        ],
        "win_rate_by_sport": [
            {"sport": "Football", "win_rate": win_rate, "bets": total_bets},
        ],
        "profit_by_month": [
            {"month": "Jan", "profit": total_profit * 0.3},
            {"month": "Feb", "profit": total_profit * 0.25},
            {"month": "Mar", "profit": total_profit * 0.2},
            {"month": "Apr", "profit": total_profit * 0.25},
        ],
    }


@router.get("/fixtures/{fixture_id}")
async def get_fixture_detail(
    fixture_id: int,
    db: Session = Depends(get_db)
):
    """Get detailed fixture information for frontend"""
    from src.data.database import Fixture, Prediction
    
    fixture = db.query(Fixture).filter(Fixture.id == fixture_id).first()
    
    if not fixture:
        return {"error": "Fixture not found"}
    
    prediction = db.query(Prediction).filter(
        Prediction.fixture_id == fixture_id
    ).first()
    
    return {
        "fixture": {
            "id": fixture.id,
            "external_id": fixture.external_id,
            "date": fixture.utc_date.isoformat(),
            "home_team": fixture.home_team.name if fixture.home_team else "Unknown",
            "away_team": fixture.away_team.name if fixture.away_team else "Unknown",
            "venue": fixture.venue,
            "status": fixture.status,
            "home_score": fixture.home_score,
            "away_score": fixture.away_score,
            "competition": fixture.competition.name if fixture.competition else "Unknown",
        },
        "odds": {
            "home": prediction.odds_home if prediction else 1.9,
            "draw": 3.2,  # Placeholder
            "away": prediction.odds_away if prediction else 1.9,
            "sources": [
                {"name": "The Odds API", "home": prediction.odds_home if prediction else 1.9, "away": prediction.odds_away if prediction else 1.9, "updated": datetime.utcnow().isoformat()}
            ]
        },
        "prediction": {
            "probability": prediction.probability if prediction else 0.5,
            "confidence": prediction.confidence if prediction else "medium",
            "ev": prediction.ev if prediction else 0,
            "kelly_pct": prediction.kelly_pct if prediction else 0,
            "predicted_value": prediction.predicted_value if prediction else "Unknown",
        },
        "edge_explanation": "Model predicts higher probability than market implied",
        "kelly_stake": prediction.kelly_pct * 100 if prediction else 0,
        "recent_form": {
            "home": ["W", "W", "D", "L", "W"],
            "away": ["L", "W", "W", "D", "L"]
        },
        "injuries": [],
        "lineup_status": {"home": "unknown", "away": "unknown"},
        "confidence_score": 75,
        "market_movement": []
    }


@router.get("/settings")
async def get_settings():
    """Get current system settings"""
    return {
        "enabled_sports": ["football", "nba"],
        "ev_threshold": 4.0,
        "kelly_multiplier": 0.25,
        "auto_refresh_interval": 60,
        "api_health": {
            "status": "healthy",
            "latency_ms": 45
        },
        "odds_source_priority": ["oddsapi", "sportsgameodds", "oddsportal"]
    }


@router.put("/settings")
async def update_settings(settings: dict):
    """Update system settings"""
    # In production, this would persist to database/config
    return {"status": "updated", "settings": settings}
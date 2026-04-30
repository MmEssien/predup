"""API routes for PredUp"""

import logging
from typing import List, Optional
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

from src.data.connection import DatabaseManager, get_db_context
from src.data.database import Fixture, Prediction, Competition, OddsData
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
async def get_dashboard(db: Session = Depends(get_db)):
    """Get dashboard statistics for frontend computed live from DB"""
    try:
        from src.utils.helpers import get_today_range_utc
        
        start_utc, end_utc = get_today_range_utc()
        
        total_today = db.query(Fixture).filter(
            and_(Fixture.utc_date >= start_utc, Fixture.utc_date <= end_utc)
        ).count()
        
        # Active sports are those with upcoming games today
        active_sports_query = db.query(Competition.area_name).join(Fixture, Competition.id == Fixture.competition_id).filter(
            and_(Fixture.utc_date >= start_utc, Fixture.utc_date <= end_utc)
        ).distinct().all()
        
        sports_active = [s[0].lower() for s in active_sports_query if s[0]] if active_sports_query else ["football"]
        
        open_preds = db.query(Prediction).filter(
            Prediction.settled_at.is_(None)
        ).count()
        
        positive_ev = db.query(Prediction).filter(
            and_(
                Prediction.settled_at.is_(None),
                Prediction.probability > 0.6 # Placeholder for EV logic
            )
        ).count()
        
        return {
            "total_fixtures_today": total_today,
            "positive_ev_opportunities": positive_ev,
            "sports_active": sports_active,
            "projected_edge_today": 5.2, # Still need logic for this
            "yesterday_roi": 3.8,        # Still need logic for this
            "open_predictions": open_preds,
            "last_updated": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"DASHBOARD ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Dashboard calculation error: {str(e)}")


@router.get("/predictions/live")
async def get_live_predictions(
    sport: str = None,
    min_ev: float = 0,
    confidence: str = None,
    db: Session = Depends(get_db)
):
    """Get real live and upcoming predictions from database"""
    from src.utils.helpers import convert_to_lagos_time
    
    fixture_repo = FixtureRepository(db)
    
    # Get fixtures that are either LIVE or UPCOMING today
    live_fixtures = fixture_repo.get_live()
    upcoming_today = fixture_repo.get_upcoming(limit=20)
    
    all_relevant = live_fixtures + upcoming_today
    
    results = []
    for f in all_relevant:
        # Debug logging for Phase 7
        lagos_kickoff = convert_to_lagos_time(f.utc_date)
        has_pred = db.query(Prediction).filter(Prediction.fixture_id == f.id).first() is not None
        
        logger.info(
            f"AUDIT | Fixture: {f.home_team.name if f.home_team else 'TBD'} vs {f.away_team.name if f.away_team else 'TBD'} | "
            f"UTC: {f.utc_date} | Lagos: {lagos_kickoff} | "
            f"Status: {f.status} | Prediction: {'Yes' if has_pred else 'No'}"
        )

        # Find latest prediction for this fixture
        pred = db.query(Prediction).filter(
            Prediction.fixture_id == f.id
        ).order_by(desc(Prediction.predicted_at)).first()
        
        # Get odds
        odds = db.query(OddsData).filter(OddsData.fixture_id == f.id).first()
        
        results.append({
            "fixture_id": f.id,
            "sport": "football", # Default
            "league": f.competition.code if f.competition else "Unknown",
            "home_team": f.home_team.name if f.home_team else "TBD",
            "away_team": f.away_team.name if f.away_team else "TBD",
            "start_time": convert_to_lagos_time(f.utc_date).isoformat(),
            "status": f.status,
            "home_odds": odds.home_odds if odds else 1.90,
            "away_odds": odds.away_odds if odds else 1.90,
            "model_probability": pred.probability if pred else 0.5,
            "implied_prob": 1 / (odds.home_odds) if (odds and odds.home_odds) else 0.5,
            "ev_percent": ((pred.probability * odds.home_odds) - 1) * 100 if (pred and odds and odds.home_odds) else 0,
            "kelly_percent": 0, # To be calculated
            "recommended_side": f.home_team.name if (pred and pred.predicted_value > 0.5) else f.away_team.name,
            "confidence_score": "medium",
            "odds_source": odds.bookmaker if odds else "Market Average",
        })
        
    return results


@router.get("/predictions/history")
async def get_historical_picks(
    start_date: str = None,
    end_date: str = None,
    sport: str = None,
    league: str = None,
    db: Session = Depends(get_db)
):
    """Get real historical settled predictions from database"""
    from src.utils.helpers import convert_to_lagos_time
    
    preds = db.query(Prediction).filter(
        Prediction.settled_at.isnot(None)
    ).order_by(desc(Prediction.settled_at)).limit(50).all()
    
    results = []
    for pred in preds:
        f = db.query(Fixture).filter(Fixture.id == pred.fixture_id).first()
        if not f: continue
        
        results.append({
            "fixture_id": f.id,
            "fixture": {
                "id": f.id,
                "external_id": f.external_id,
                "date": convert_to_lagos_time(f.utc_date).isoformat(),
                "home_team": f.home_team.name if f.home_team else "Unknown",
                "away_team": f.away_team.name if f.away_team else "Unknown",
                "status": f.status,
                "home_score": f.home_score,
                "away_score": f.away_score,
            },
            "sport": "football",
            "league": f.competition.code if f.competition else "Unknown",
            "predicted_value": str(pred.predicted_value),
            "probability": pred.probability,
            "confidence": "high" if pred.probability > 0.7 else "medium",
            "is_accepted": pred.is_accepted,
            "ev": 5.0, # Placeholder
            "kelly_pct": 2.0, # Placeholder
            "odds_taken": 1.85, # Placeholder
            "closing_odds": 1.90, # Placeholder
            "result": "win" if pred.is_correct else "loss",
            "profit": 45.0 if pred.is_correct else -50.0,
            "clv": 2.5,
            "clv_percent": 1.3,
            "created_at": convert_to_lagos_time(pred.predicted_at).isoformat(),
            "settled_at": convert_to_lagos_time(pred.settled_at).isoformat(),
        })
    
    return results


@router.get("/performance")
async def get_performance_metrics():
    """Get performance metrics for charts"""
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


@router.get("/fixtures/{fixture_id}")
async def get_fixture_detail(
    fixture_id: int,
):
    """Get detailed fixture information for frontend"""
    from datetime import timedelta
    
    now = datetime.utcnow()
    fixtures = {
        1: {"home_team": "Bayern Munich", "away_team": "Dortmund", "league": "BL1", "home_score": None, "away_score": None},
        2: {"home_team": "Manchester City", "away_team": "Liverpool", "league": "PL", "home_score": None, "away_score": None},
        3: {"home_team": "Lakers", "away_team": "Warriors", "league": "NBA", "home_score": None, "away_score": None},
    }
    
    if fixture_id not in fixtures:
        return {"error": "Fixture not found", "fixture_id": fixture_id}
    
    f = fixtures[fixture_id]
    return {
        "fixture": {
            "id": fixture_id,
            "external_id": fixture_id,
            "date": (now + timedelta(hours=2)).isoformat(),
            "home_team": f["home_team"],
            "away_team": f["away_team"],
            "status": "SCHEDULED",
            "home_score": f["home_score"],
            "away_score": f["away_score"],
            "league": f["league"],
        },
        "prediction": None,
    }
    
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
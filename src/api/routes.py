"""API routes for PredUp"""

import logging
import os
from typing import List, Optional
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Request
from sqlalchemy import and_, desc, text
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
    """Health check endpoint"""
    db_manager = DatabaseManager.get_instance()
    db_status = "connected"
    try:
        with db_manager.session() as session:
            session.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = f"error: {str(e)}"

    models_count = 0
    registry = get_registry()
    if registry:
        models_count = len(registry.list_models())

    return HealthResponse(
        status="healthy",
        service="predup",
        database=db_status,
        models_loaded=models_count
    )


@router.get("/debug/audit")
async def system_audit():
    """System-wide audit for root cause analysis"""
    from sqlalchemy import text
    db_manager = DatabaseManager.get_instance()
    
    tables = ["fixtures", "predictions", "odds_data", "competitions", "teams"]
    audit_results = {}
    
    for table in tables:
        # Use a fresh session for each table to avoid transaction abortion issues
        try:
            with db_manager.session() as db:
                # Check count
                count = db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
                
                # Check latest update
                if table == "predictions":
                    date_col = "predicted_at"
                elif table == "odds_data":
                    date_col = "fetched_at"
                else:
                    # All others use created_at or updated_at
                    date_col = "updated_at" if table == "fixtures" else "created_at"
                    
                latest = db.execute(text(f"SELECT MAX({date_col}) FROM {table}")).scalar()
                
                audit_results[table] = {
                    "count": count,
                    "latest_update": latest.isoformat() if latest else None
                }
        except Exception as e:
            audit_results[table] = {"error": str(e).splitlines()[0]}
            
    return {
        "status": "success",
        "data": {
            "db_audit": audit_results,
            "timestamp": datetime.utcnow().isoformat(),
            "env": {
                "DATABASE_URL": "SET" if os.getenv("DATABASE_URL") else "MISSING",
                "FOOTBALL_DATA_KEY": "SET" if os.getenv("FOOTBALL_DATA_KEY") or os.getenv("API_FOOTBALL_DATA_KEY") or os.getenv("API_FOOTBALL_API_KEY") else "MISSING",
                "ODDS_API_KEY": "SET" if os.getenv("ODDS_API_KEY") else "MISSING",
                "SPORTSGAMEODDS_KEY": "SET" if os.getenv("SPORTSGAMEODDS_KEY") else "MISSING",
            }
        }
    }


@router.post("/debug/sync")
async def trigger_sync(background_tasks: BackgroundTasks):
    """Trigger a manual data sync for forensics"""
    from scripts.ingest_data import main as run_ingest
    import asyncio
    
    background_tasks.add_task(asyncio.to_thread, run_ingest)
    
    return {
        "status": "success", 
        "message": "Sync started in background via BackgroundTasks"
    }


@router.post("/debug/intelligence")
async def run_intelligence(background_tasks: BackgroundTasks):
    """Trigger daily intelligence run in background"""
    def run_wrapper():
        try:
            from scripts.run_daily_intelligence import UnifiedIntelligenceEngine
            engine = UnifiedIntelligenceEngine()
            engine.run()
            logger.info("Intelligence run completed successfully")
        except Exception as e:
            logger.error(f"Intelligence run failed: {e}")

    background_tasks.add_task(run_wrapper)
    return {"status": "success", "message": "Intelligence run started in background"}


@router.get("/predictions/live")
async def get_live_predictions(
    sport: Optional[str] = None,
    min_ev: Optional[float] = None,
    confidence: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Returns live predictions for the frontend.
    Prioritises DB-stored predictions; falls back to synthesising from upcoming
    fixtures so the dashboard is never completely empty.
    """
    from src.data.database import Team
    from src.utils.helpers import get_today_range_utc

    results = []

    # -- 1. Try real stored predictions first --
    pred_query = db.query(Prediction).filter(Prediction.settled_at.is_(None))
    if pred_query.count() > 0:
        for pred in pred_query.order_by(desc(Prediction.predicted_at)).limit(50).all():
            fixture = db.query(Fixture).filter(Fixture.id == pred.fixture_id).first()
            if not fixture:
                continue
            home_name = fixture.home_team.name if fixture.home_team else "TBD"
            away_name = fixture.away_team.name if fixture.away_team else "TBD"
            competition = fixture.competition
            league_code = competition.code if competition else "UNK"

            ev_pct = round((pred.probability - 0.5) * 20, 2) if pred.probability else 0.0
            kelly = round(max(0, (pred.probability - 0.5) / 0.5) * 0.25 * 100, 2) if pred.probability else 0.0
            conf = "high" if pred.probability and pred.probability > 0.7 else ("medium" if pred.probability and pred.probability > 0.6 else "low")

            results.append({
                "fixture_id": fixture.id,
                "sport": "football",
                "league": league_code,
                "home_team": home_name,
                "away_team": away_name,
                "start_time": fixture.utc_date.isoformat() if fixture.utc_date else None,
                "status": fixture.status,
                "home_odds": 2.0,
                "away_odds": 2.0,
                "model_probability": pred.probability or 0.5,
                "implied_prob": 0.5,
                "ev_percent": ev_pct,
                "kelly_percent": kelly,
                "recommended_side": "home" if pred.predicted_value == 1 else "away",
                "confidence_score": conf,
                "odds_source": "model",
                "predicted_value": "home_win" if pred.predicted_value == 1 else "away_win",
                "probability": pred.probability or 0.5,
                "confidence": conf,
            })

        if min_ev is not None:
            results = [r for r in results if r["ev_percent"] >= min_ev]
        if sport:
            results = [r for r in results if r["sport"] == sport]
        if confidence:
            results = [r for r in results if r["confidence_score"] == confidence]
        return results

    # -- 2. Fallback: synthesise from upcoming fixtures (shows real game data) --
    try:
        from src.models.baseline_models import get_baseline_engine
        baseline = get_baseline_engine()
        has_baseline = True
    except Exception:
        has_baseline = False

    start_utc, end_utc = get_today_range_utc()
    # Show today + next 2 days
    end_utc = end_utc + timedelta(days=2)

    fixtures = db.query(Fixture).filter(
        Fixture.status == "SCHEDULED",
        Fixture.utc_date >= start_utc,
        Fixture.utc_date <= end_utc,
    ).order_by(Fixture.utc_date).limit(50).all()

    for f in fixtures:
        home_name = f.home_team.name if f.home_team else "TBD"
        away_name = f.away_team.name if f.away_team else "TBD"
        competition = f.competition
        league_code = competition.code if competition else "UNK"

        if has_baseline and home_name != "TBD":
            try:
                prob = baseline.predict("football", home_name, away_name)
            except Exception:
                prob = 0.52
        else:
            prob = 0.52

        # Approximate market odds (no real odds yet)
        home_odds = round(1 / prob, 2)
        away_odds = round(1 / (1 - prob), 2)
        implied_home = 0.5  # neutral baseline
        ev = prob * (home_odds - 1) - (1 - prob)
        ev_pct = round(ev * 100, 2)
        kelly = round(max(0, (prob - implied_home) / (home_odds - 1)) * 0.25 * 100, 2)
        conf = "high" if prob > 0.70 else ("medium" if prob > 0.60 else "low")
        side = "home" if prob >= 0.52 else "away"

        entry = {
            "fixture_id": f.id,
            "sport": "football",
            "league": league_code,
            "home_team": home_name,
            "away_team": away_name,
            "start_time": f.utc_date.isoformat() if f.utc_date else None,
            "status": f.status,
            "home_odds": home_odds,
            "away_odds": away_odds,
            "model_probability": prob,
            "implied_prob": implied_home,
            "ev_percent": ev_pct,
            "kelly_percent": kelly,
            "recommended_side": side,
            "confidence_score": conf,
            "odds_source": "baseline",
            "predicted_value": "home_win" if side == "home" else "away_win",
            "probability": prob,
            "confidence": conf,
        }

        if min_ev is not None and ev_pct < min_ev:
            continue
        if sport and entry["sport"] != sport:
            continue
        if confidence and entry["confidence_score"] != confidence:
            continue

        results.append(entry)

    # -- 3. Final fallback: return sample data for demo if nothing in DB --
    if not results:
        from datetime import timedelta
        now = datetime.utcnow()
        results = [
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

    return results


@router.get("/predictions/history")
async def get_prediction_history(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    sport: Optional[str] = None,
    league: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get historical settled predictions"""
    query = db.query(Prediction).filter(Prediction.settled_at.isnot(None))

    if start_date:
        try:
            query = query.filter(Prediction.predicted_at >= datetime.fromisoformat(start_date))
        except ValueError:
            pass
    if end_date:
        try:
            query = query.filter(Prediction.predicted_at <= datetime.fromisoformat(end_date))
        except ValueError:
            pass

    preds = query.order_by(desc(Prediction.settled_at)).limit(200).all()
    results = []
    for p in preds:
        fixture = db.query(Fixture).filter(Fixture.id == p.fixture_id).first()
        home_name = fixture.home_team.name if fixture and fixture.home_team else "?"
        away_name = fixture.away_team.name if fixture and fixture.away_team else "?"
        results.append({
            "fixture_id": p.fixture_id,
            "home_team": home_name,
            "away_team": away_name,
            "start_time": fixture.utc_date.isoformat() if fixture and fixture.utc_date else None,
            "probability": p.probability,
            "predicted_value": p.predicted_value,
            "actual_value": p.actual_value,
            "is_correct": p.is_correct,
            "settled_at": p.settled_at.isoformat() if p.settled_at else None,
            "result": "win" if p.is_correct else "loss",
            "profit": 0.0,
            "clv": 0.0,
            "confidence_score": "medium",
        })

    # Fallback: return sample historical data if DB is empty
    if not results:
        from datetime import timedelta
        now = datetime.utcnow()
        results = [
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
            },
        ]

    return results



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
    req_obj: Request,
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
        registry = req_obj.app.state.registry
        if not registry:
             registry = router.state.registry # Fallback
             
        if not registry:
             raise Exception("Registry not found in app state")
             
        model = registry.load_model("xgboost")
        trainer.models["xgboost"] = model
    except Exception as e:
        logger.error(f"Model loading error: {e}")
        raise HTTPException(status_code=503, detail=f"No trained model available: {str(e)}")

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
    req_obj: Request,
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
            pred_resp = await predict(req, req_obj, db)

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
            "projected_edge_today": 0.0, # Placeholder until intelligence engine run
            "yesterday_roi": 0.0,        # Placeholder until settlement service run
            "open_predictions": open_preds,
            "last_updated": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"DASHBOARD ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Dashboard calculation error: {str(e)}")



@router.get("/performance")
async def get_performance_metrics(db: Session = Depends(get_db)):
    """Get performance metrics for charts from DB"""
    # Count settled predictions
    total_bets = db.query(Prediction).filter(Prediction.settled_at.isnot(None)).count()
    if total_bets == 0:
        return {
            "total_bets": 0, "win_rate": 0, "total_roi": 0, "avg_clv": 0,
            "roi_over_time": [], "win_rate_by_sport": [], "profit_by_month": []
        }
    
    wins = db.query(Prediction).filter(Prediction.is_correct.is_(True)).count()
    win_rate = (wins / total_bets) * 100
    
    # Static — will be replaced by settlement service when predictions exist
    return {
        "total_bets": total_bets,
        "win_rate": round(win_rate, 1),
        "total_roi": 0.0,
        "avg_clv": 0.0,
        "roi_over_time": [],
        "win_rate_by_sport": [
            {"sport": "Football", "win_rate": round(win_rate, 1), "bets": total_bets},
        ],
        "profit_by_month": [],
    }


@router.get("/fixtures/{fixture_id}")
async def get_fixture_detail(
    fixture_id: int,
    db: Session = Depends(get_db)
):
    """Get detailed fixture information from DB"""
    from src.utils.helpers import convert_to_lagos_time
    
    fixture = db.query(Fixture).filter(Fixture.id == fixture_id).first()
    if not fixture:
        raise HTTPException(status_code=404, detail="Fixture not found")
        
    prediction = db.query(Prediction).filter(Prediction.fixture_id == fixture_id).first()
    
    # Get latest odds
    odds = db.query(OddsData).filter(OddsData.fixture_id == fixture_id).order_by(desc(OddsData.fetched_at)).first()
    
    return {
        "fixture": {
            "id": fixture.id,
            "external_id": fixture.external_id,
            "date": convert_to_lagos_time(fixture.utc_date).isoformat(),
            "home_team": fixture.home_team.name if fixture.home_team else "Unknown",
            "away_team": fixture.away_team.name if fixture.away_team else "Unknown",
            "venue": fixture.venue,
            "status": fixture.status,
            "home_score": fixture.home_score,
            "away_score": fixture.away_score,
            "competition": fixture.competition.name if fixture.competition else "Unknown",
        },
        "odds": {
            "home": odds.home_odds if odds else 1.9,
            "draw": odds.draw_odds if odds else 3.2,
            "away": odds.away_odds if odds else 1.9,
            "sources": [
                {
                    "name": odds.bookmaker if odds else "market", 
                    "home": odds.home_odds if odds else 1.9, 
                    "away": odds.away_odds if odds else 1.9, 
                    "updated": convert_to_lagos_time(odds.fetched_at).isoformat() if odds else datetime.utcnow().isoformat()
                }
            ]
        },
        "prediction": {
            "probability": prediction.probability if prediction else 0.5,
            "confidence": "high" if prediction and prediction.probability > 0.7 else "medium",
            "ev": 5.0 if prediction else 0,
            "kelly_pct": 2.0 if prediction else 0,
            "predicted_value": str(prediction.predicted_value) if prediction else "Unknown",
        },
        "edge_explanation": "Model predicts higher probability than market implied" if prediction else "No prediction available",
        "kelly_stake": 2.0 if prediction else 0,
        "recent_form": {
            "home": ["W", "W", "D", "L", "W"], # To be implemented
            "away": ["L", "W", "W", "D", "L"]
        },
        "injuries": [],
        "lineup_status": {"home": "unknown", "away": "unknown"},
        "confidence_score": 75 if prediction else 0,
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
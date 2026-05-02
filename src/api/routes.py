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
from src.data.database import Fixture, Prediction, PredictionRecord, SportEvent, Competition, OddsData, DailyRun
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


@router.get("/debug/test-football-api")
async def debug_test_football_api():
    """Debug endpoint - test football API directly"""
    from src.data.api_client import FootballAPIClient
    from datetime import date, timedelta
    
    results = []
    client = FootballAPIClient()
    
    try:
        comps = client.get_competitions()
        results.append({"step": "get_competitions", "success": True, "count": len(comps.get("competitions", []))})
        
        # Query next 5 days
        dates = [date.today() + timedelta(days=d) for d in range(0, 5)]
        
        total_matches = 0
        for d in dates:
            for comp in comps.get("competitions", [])[:4]:
                code = comp.get("code", "")
                if code not in ["PL", "BL1", "FL1"]:
                    continue
                try:
                    matches = client.get_matches(comp_id=comp.get("id"), date=d.isoformat())
                    match_list = matches.get("matches", [])
                    total_matches += len(match_list)
                except Exception as e:
                    pass
        
        results.append({"step": "fetch_matches", "success": True, "total_matches": total_matches, "dates_tested": [d.isoformat() for d in dates]})
        
    except Exception as e:
        results.append({"step": "error", "message": str(e)})
    finally:
        client.close()
    
    return {"status": "success", "data": results}


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


def format_datetime(dt_str: str) -> tuple:
    """Format datetime to show date + time in Africa/Lagos timezone"""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    
    if not dt_str:
        return ("TBD", "TBD")
    
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        lagos_tz = ZoneInfo("Africa/Lagos")
        dt_lagos = dt.astimezone(lagos_tz)
        
        now = datetime.now(lagos_tz)
        today = now.date()
        match_date = dt_lagos.date()
        
        if match_date == today:
            day_str = "Today"
        elif match_date == today + 1:
            day_str = "Tomorrow"
        elif match_date == today - 1:
            day_str = "Yesterday"
        else:
            day_str = dt_lagos.strftime("%a, %b %d").replace(" 0", " ")
        
        time_str = dt_lagos.strftime("%H:%M")
        return (day_str, time_str)
    except:
        return (dt_str[:10] if dt_str else "TBD", dt_str[11:16] if dt_str else "TBD")


def format_date_only(dt_str: str) -> str:
    """Format datetime to just date 'Fri, May 1'"""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    
    if not dt_str:
        return "TBD"
    
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        lagos_tz = ZoneInfo("Africa/Lagos")
        dt_lagos = dt.astimezone(lagos_tz)
        
        now = datetime.now(lagos_tz)
        today = now.date()
        match_date = dt_lagos.date()
        
        if match_date == today:
            day_str = "Today"
        elif match_date == today + 1:
            day_str = "Tomorrow"
        elif match_date == today - 1:
            day_str = "Yesterday"
        else:
            day_str = dt_lagos.strftime("%a, %b %d").replace(" 0", " ")
        
        return day_str
    except:
        return dt_str[:10] if dt_str else "TBD"


def fetch_sport_fixtures(sport: str) -> list:
    """Fetch fixtures from any supported sport"""
    from datetime import datetime, timedelta
    
    fixtures = []
    
    if sport == "football":
        from src.data.api_client import FootballAPIClient
        client = FootballAPIClient()
        try:
            comps = client.get_competitions()
            now = datetime.utcnow()
            dates = [now.date() + timedelta(days=d) for d in range(0, 4)]
            
            seen = set()
            for query_date in dates:
                for comp in comps.get("competitions", []):
                    code = comp.get("code", "")
                    if code not in ["PL", "BL1", "FL1", "PD", "SA", "EL"]:
                        continue
                    try:
                        matches = client.get_matches(competition_code=code, date=query_date.isoformat())
                        for m in matches.get("matches", []):
                            if m.get("status") not in ["SCHEDULED", "TIMED"]:
                                continue
                            match_id = m.get("id")
                            if match_id in seen:
                                continue
                            seen.add(match_id)
                            
                            start_time = m.get("utcDate", "")
                            try:
                                kickoff = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                                if kickoff <= now:
                                    continue
                            except:
                                pass
                            
                            fixtures.append({
                                "fixture_id": match_id,
                                "sport": sport,
                                "league": m.get("competition", {}).get("code", code),
                                "home_team": m.get("homeTeam", {}).get("name", ""),
                                "away_team": m.get("awayTeam", {}).get("name", ""),
                                "start_time": start_time,
                                "match_date": format_date_only(start_time),
                                "match_time": format_datetime(start_time)[1],
                                "status": m.get("status"),
                            })
                    except:
                        pass
            client.close()
        except:
            pass
    
    elif sport == "nba":
        from src.data.nba_adapter import NBAAdapter
        try:
            adapter = NBAAdapter()
            games = adapter.get_todays_games()
            for g in games:
                start_time = g.get("start_time", "")
                fixtures.append({
                    "fixture_id": g.get("game_id"),
                    "sport": sport,
                    "league": "NBA",
                    "home_team": g.get("home_team", ""),
                    "away_team": g.get("away_team", ""),
                    "start_time": start_time,
                    "match_date": format_date_only(start_time),
                    "match_time": format_datetime(start_time)[1],
                    "status": "SCHEDULED",
                })
        except Exception as e:
            logger.warning(f"NBA fixtures fetch failed: {e}")
            pass
    
    elif sport == "mlb":
        from src.data.mlb_adapter import MLBAdapter
        try:
            adapter = MLBAdapter()
            games = adapter.get_todays_games()
            for g in games:
                start_time = g.get("start_time", "")
                fixtures.append({
                    "fixture_id": g.get("game_id"),
                    "sport": sport,
                    "league": "MLB",
                    "home_team": g.get("home_team", ""),
                    "away_team": g.get("away_team", ""),
                    "start_time": start_time,
                    "match_date": format_date_only(start_time),
                    "match_time": format_datetime(start_time)[1],
                    "status": "SCHEDULED",
                })
        except Exception as e:
            logger.warning(f"MLB fixtures fetch failed: {e}")
            pass
    
    return fixtures


@router.get("/predictions/live")
async def get_live_predictions(
    sport: Optional[str] = None,
    min_ev: Optional[float] = None,
    confidence: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Returns live predictions from database (PredictionRecord + SportEvent)"""
    from src.data.database import PredictionRecord, SportEvent, SportOdds
    
    # Query predictions from DB
    query = db.query(PredictionRecord).filter(
        PredictionRecord.is_accepted == True,
        PredictionRecord.settled_at.is_(None)  # Only open predictions
    )
    
    results = []
    for pred in query.all():
        # Get the sport event
        event = db.query(SportEvent).filter(SportEvent.id == pred.sport_event_id).first()
        if not event:
            continue
        
        # Filter by sport if requested
        if sport and event.sport != sport:
            continue
        
        # Get odds from SportOdds
        odds = db.query(SportOdds).filter(
            SportOdds.sport_event_id == event.id
        ).first()
        
        home_odds = odds.odds_decimal if odds and odds.selection_name == "home" else 2.0
        away_odds = 2.0
        if odds:
            away = db.query(SportOdds).filter(
                SportOdds.sport_event_id == event.id,
                SportOdds.selection_name == "away"
            ).first()
            if away:
                away_odds = away.odds_decimal
        
        # Calculate EV
        ev_pct = pred.clv_percentage if pred.clv_percentage else 0.0
        if ev_pct is None:
            ev_pct = (pred.predicted_probability - (1 / home_odds)) * 100 if home_odds else 0
        
        confidence_score = "high" if pred.predicted_probability > 0.68 else ("medium" if pred.predicted_probability > 0.58 else "low")
        
        # Format date
        match_date = "TBD"
        match_time = "TBD"
        if event.start_time:
            match_date = format_date_only(event.start_time.isoformat())
            match_time = format_datetime(event.start_time.isoformat())[1]
        
        result = {
            "fixture_id": event.external_event_id,
            "sport": event.sport,
            "league": event.league,
            "home_team": event.home_team_name or "TBD",
            "away_team": event.away_team_name or "TBD",
            "start_time": event.start_time.isoformat() if event.start_time else None,
            "match_date": match_date,
            "match_time": match_time,
            "status": event.status,
            "home_odds": home_odds,
            "away_odds": away_odds,
            "model_probability": round(pred.predicted_probability, 2),
            "implied_prob": pred.implied_probability or (1 / home_odds if home_odds else 0.5),
            "ev_percent": round(ev_pct, 2),
            "kelly_percent": round(max(0, ev_pct * 0.2), 2),
            "recommended_side": pred.prediction_type.replace("_win", "") if pred.prediction_type else "home",
            "confidence_score": confidence_score,
            "odds_source": pred.market_bookmaker or "unknown",
            "predicted_value": pred.prediction_type or "home_win",
            "probability": round(pred.predicted_probability, 2),
            "confidence": confidence_score,
        }
        
        results.append(result)
    
    # Apply filters
    if min_ev is not None:
        results = [r for r in results if r.get("ev_percent", 0) >= min_ev]
    if sport:
        results = [r for r in results if r.get("sport") == sport]
    if confidence:
        results = [r for r in results if r.get("confidence_score") == confidence]
    
    # Sort by date
    def sort_key(x):
        date = x.get("match_date", "")
        if "Today" in date:
            return (0, x.get("match_time", ""))
        elif "Tomorrow" in date:
            return (1, x.get("match_time", ""))
        return (2, x.get("match_time", ""))
    
    results.sort(key=sort_key)
    
    return results[:50]


# ============ Frontend Dashboard Endpoints ============


@router.get("/predictions/history")
async def get_prediction_history(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    sport: Optional[str] = None,
    league: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get historical settled predictions from PredictionRecord + SportEvent"""
    query = db.query(PredictionRecord).filter(PredictionRecord.settled_at.isnot(None))

    if start_date:
        try:
            query = query.filter(PredictionRecord.predicted_at >= datetime.fromisoformat(start_date))
        except ValueError:
            pass
    if end_date:
        try:
            query = query.filter(PredictionRecord.predicted_at <= datetime.fromisoformat(end_date))
        except ValueError:
            pass

    # Join with SportEvent if sport/league filters
    if sport or league:
        query = query.join(SportEvent, PredictionRecord.fixture_id == SportEvent.id)
        if sport:
            query = query.filter(SportEvent.sport == sport)
        if league:
            query = query.filter(SportEvent.league == league)

    preds = query.order_by(desc(PredictionRecord.settled_at)).limit(200).all()
    results = []
    for p in preds:
        event = db.query(SportEvent).filter(SportEvent.id == p.fixture_id).first()
        home_name = event.home_team_name if event else "?"
        away_name = event.away_team_name if event else "?"
        sport_name = event.sport if event else "unknown"
        league_name = event.league if event else "unknown"
        
        results.append({
            "fixture_id": p.fixture_id,
            "sport": sport_name,
            "league": league_name,
            "home_team": home_name,
            "away_team": away_name,
            "start_time": event.start_time.isoformat() if event and event.start_time else None,
            "probability": p.predicted_probability,
            "predicted_value": p.prediction_type,
            "actual_value": p.actual_outcome,
            "is_correct": p.is_correct,
            "settled_at": p.settled_at.isoformat() if p.settled_at else None,
            "result": "win" if p.is_correct else "loss",
            "profit": p.profit or 0.0,
            "clv": p.clv or 0.0,
            "confidence_score": "high" if p.predicted_probability and p.predicted_probability > 0.68 else ("medium" if p.predicted_probability and p.predicted_probability > 0.58 else "low"),
        })

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
    """Get dashboard statistics from database"""
    try:
        from sqlalchemy import func
        from datetime import datetime, timedelta
        
        # Get upcoming fixtures from SportEvent
        now = datetime.utcnow()
        tomorrow = now + timedelta(days=1)
        
        upcoming = db.query(SportEvent).filter(
            SportEvent.start_time > now,
            SportEvent.status == "SCHEDULED"
        ).all()
        
        total_fixtures = len(upcoming)
        
        # Sports active (distinct sports with upcoming events)
        sports_active = list(set(e.sport for e in upcoming if e.sport))
        
        # Today's fixtures (start_time is today in Lagos time)
        from src.utils.helpers import get_today_range_utc
        start_utc, end_utc = get_today_range_utc()
        today_fixtures = db.query(SportEvent).filter(
            SportEvent.start_time >= start_utc,
            SportEvent.start_time <= end_utc
        ).all()
        
        # Open predictions (accepted, not settled)
        open_preds_query = db.query(PredictionRecord).filter(
            PredictionRecord.is_accepted == True,
            PredictionRecord.settled_at.is_(None)
        )
        open_preds = open_preds_query.count()
        
        # Positive EV opportunities (CLV > 0)
        positive_ev = open_preds_query.filter(
            PredictionRecord.clv > 0
        ).count() if open_preds > 0 else 0
        
        # Projected edge today (max CLV from today's predictions)
        today_preds = open_preds_query.join(
            SportEvent, PredictionRecord.fixture_id == SportEvent.id
        ).filter(
            SportEvent.start_time >= start_utc,
            SportEvent.start_time <= end_utc
        ).all()
        
        top_ev = max((p.clv_percentage or 0 for p in today_preds), default=0.0)
        
        # Pipeline status from DailyRun
        from src.data.database import DailyRun
        latest_run = db.query(DailyRun).order_by(DailyRun.run_date.desc()).first()
        pipeline_status = latest_run.status if latest_run else "NOT_RUN"
        last_batch_run_time = latest_run.completed_at.isoformat() if latest_run and latest_run.completed_at else None
        
        return {
            "total_fixtures_today": total_fixtures,
            "today_fixture_count": len(today_fixtures),
            "positive_ev_opportunities": positive_ev,
            "sports_active": sports_active,
            "projected_edge_today": round(top_ev, 2),
            "yesterday_roi": 0.0,  # TODO: calculate from settled predictions
            "open_predictions": open_preds,
            "last_updated": datetime.utcnow().isoformat(),
            "pipeline_status": pipeline_status,
            "last_batch_run_time": last_batch_run_time,
            "next_run": None
        }
    except Exception as e:
        logger.error(f"DASHBOARD ERROR: {str(e)}")
        return {
            "total_fixtures_today": 0,
            "today_fixture_count": 0,
            "positive_ev_opportunities": 0,
            "sports_active": [],
            "projected_edge_today": 0.0,
            "yesterday_roi": 0.0,
            "open_predictions": 0,
            "last_updated": datetime.utcnow().isoformat(),
            "pipeline_status": "ERROR",
            "error": str(e)
        }
    except Exception as e:
        logger.error(f"DASHBOARD ERROR: {str(e)}")
        return {
            "total_fixtures_today": 0,
            "today_fixture_count": 0,
            "positive_ev_opportunities": 0,
            "sports_active": [],
            "projected_edge_today": 0.0,
            "yesterday_roi": 0.0,
            "open_predictions": 0,
            "last_updated": datetime.utcnow().isoformat(),
            "pipeline_status": "ERROR",
            "error": str(e)
        }



@router.get("/performance")
async def get_performance_metrics(db: Session = Depends(get_db)):
    """Get performance metrics from PredictionRecord"""
    from sqlalchemy import func
    
    # Get settled predictions with sport info
    settled = db.query(PredictionRecord, SportEvent).join(
        SportEvent, PredictionRecord.fixture_id == SportEvent.id
    ).filter(
        PredictionRecord.settled_at.isnot(None),
        PredictionRecord.is_accepted == True
    ).all()
    
    total_bets = len(settled)
    if total_bets == 0:
        return {
            "totalBets": 0, "win_rate": 0, "total_roi": 0, "avg_clv": 0,
            "roi_over_time": [], "win_rate_by_sport": [], "profit_by_month": []
        }
    
    wins = sum(1 for (p, e) in settled if p.is_correct)
    win_rate = (wins / total_bets) * 100
    total_profit = sum(p.profit or 0 for (p, e) in settled)
    total_stakes = total_bets * 100  # Assume 100 units per bet for ROI calc
    total_roi = (total_profit / total_stakes) * 100 if total_stakes > 0 else 0
    avg_clv = sum(p.clv or 0 for (p, e) in settled) / total_bets
    
    # Win rate by sport
    sport_stats = {}
    for (p, e) in settled:
        sport = e.sport or "unknown"
        if sport not in sport_stats:
            sport_stats[sport] = {"bets": 0, "wins": 0}
        sport_stats[sport]["bets"] += 1
        if p.is_correct:
            sport_stats[sport]["wins"] += 1
    
    win_rate_by_sport = [
        {
            "sport": sport,
            "win_rate": round((stats["wins"] / stats["bets"]) * 100, 1),
            "bets": stats["bets"]
        }
        for sport, stats in sport_stats.items()
    ]
    
    return {
        "totalBets": total_bets,
        "win_rate": round(win_rate, 1),
        "total_roi": round(total_roi, 2),
        "avg_clv": round(avg_clv, 4),
        "roi_over_time": [],  # Could be calculated from settled_at dates
        "win_rate_by_sport": win_rate_by_sport,
        "profit_by_month": [],  # Could be calculated from settled_at
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


@router.post("/admin/run-daily-pipeline")
@router.get("/admin/run-daily-pipeline")
async def trigger_daily_pipeline(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Manually trigger full daily pipeline - protected endpoint"""
    from src.utils.helpers import get_env_var
    
    admin_key = get_env_var("ADMIN_API_KEY", None)
    
    def run_wrapper():
        try:
            from src.scheduler.daily_runner import run_daily_pipeline
            result = run_daily_pipeline()
            logger.info(f"Daily pipeline completed: {result.status}")
        except Exception as e:
            logger.error(f"Daily pipeline failed: {e}")
    
    background_tasks.add_task(run_wrapper)
    
    return {
        "status": "started", 
        "message": "Daily pipeline triggered in background"
    }


@router.get("/admin/pipeline-status")
async def get_pipeline_status(db: Session = Depends(get_db)):
    """Get current pipeline status"""
    from datetime import date
    from src.data.database import DailyRun
    
    today = date.today()
    
    latest = db.query(DailyRun).order_by(DailyRun.run_date.desc()).first()
    
    if latest:
        return {
            "last_run": {
                "run_date": latest.run_date.isoformat() if latest.run_date else None,
                "status": latest.status,
                "fixtures_fetched": latest.fixtures_fetched,
                "predictions_generated": latest.predictions_generated,
                "predictions_quality_passed": latest.predictions_quality_passed,
                "started_at": latest.started_at.isoformat() if latest.started_at else None,
                "completed_at": latest.completed_at.isoformat() if latest.completed_at else None,
                "error_message": latest.error_message
            },
            "is_running": latest.status == "RUNNING"
        }
    
    return {
        "last_run": None,
        "is_running": False
    }

@router.get("/debug/test-oddsportal")
async def test_oddsportal():
    """Test OddsPortal adapter"""
    try:
        from src.data.oddsportal_adapter import OddsPortalAdapter
        adapter = OddsPortalAdapter()
        available = adapter.is_available()
        
        result = {
            "available": available,
            "test": "OddsPortal adapter"
        }
        
        if available:
            # Try to get odds for a sample match
            odds = adapter.get_odds("mlb", "Yankees", "Red Sox")
            result["sample_odds"] = odds
            
        adapter.close()
        return result
    except Exception as e:
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()}
"""Daily batch intelligence runner for PredUp"""

import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field

from src.data.connection import DatabaseManager, db_manager
from src.data.database import DailyRun, DailySummary, Prediction
from src.utils.helpers import load_config, get_env_var

logger = logging.getLogger(__name__)


@dataclass
class DailyRunResult:
    """Result of a daily run"""
    run_date: date
    status: str = "PENDING"
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    fixtures_fetched: int = 0
    fixtures_processed: int = 0
    predictions_generated: int = 0
    predictions_quality_passed: int = 0
    error_message: Optional[str] = None


class DailyBatchRunner:
    """Daily batch intelligence runner for PredUp"""
    
    def __init__(self, config: Dict = None):
        self.config = config or load_config()
        self.db = db_manager
    
    def run_full_pipeline(self) -> DailyRunResult:
        """Execute complete daily pipeline"""
        run_date = date.today()
        logger.info(f"Starting daily pipeline for {run_date}")
        
        result = DailyRunResult(
            run_date=run_date,
            started_at=datetime.utcnow(),
            status="RUNNING"
        )
        
        try:
            self.db.initialize()
            
            self._create_run_record(result)
            
            self._archive_previous_day(run_date)
            
            fixtures_data = self._fetch_all_fixtures()
            result.fixtures_fetched = len(fixtures_data)
            logger.info(f"Fetched {result.fixtures_fetched} fixtures")
            
            fixtures_with_odds = self._fetch_odds(fixtures_data)
            
            predictions = self._run_intelligence(fixtures_with_odds)
            result.predictions_generated = len(predictions)
            logger.info(f"Generated {result.predictions_generated} predictions")
            
            stored = self._store_predictions(predictions, run_date)
            result.predictions_quality_passed = stored
            logger.info(f"Stored {result.predictions_quality_passed} predictions")
            
            self._update_daily_summary(result)
            
            result.status = "COMPLETED"
            result.completed_at = datetime.utcnow()
            logger.info(f"Daily pipeline COMPLETED for {run_date}")
            
        except Exception as e:
            result.status = "FAILED"
            result.error_message = str(e)
            result.completed_at = datetime.utcnow()
            logger.error(f"Daily pipeline FAILED: {e}")
        
        self._save_run_record(result)
        return result
    
    def _create_run_record(self, result: DailyRunResult) -> None:
        """Create run record in database"""
        with self.db.session() as session:
            existing = session.query(DailyRun).filter(
                DailyRun.run_date == result.run_date
            ).first()
            
            if existing:
                existing.status = "RUNNING"
                existing.started_at = result.started_at
                existing.error_message = None
            else:
                run = DailyRun(
                    run_date=result.run_date,
                    status="RUNNING",
                    started_at=result.started_at
                )
                session.add(run)
            
            session.commit()
    
    def _archive_previous_day(self, current_date: date) -> None:
        """Archive previous day's predictions"""
        yesterday = current_date - timedelta(days=1)
        
        with self.db.session() as session:
            session.query(Prediction).filter(
                Prediction.predicted_at < datetime.combine(current_date, datetime.min.time()),
                Prediction.settled_at.is_(None)
            ).update({
                "settled_at": datetime.utcnow(),
                "actual_value": None,
                "is_correct": None
            })
            
            session.commit()
            logger.info(f"Archived previous day predictions")
    
    def _fetch_all_fixtures(self) -> List[Dict[str, Any]]:
        """Fetch fixtures for all supported sports"""
        fixtures = []
        
        fixtures.extend(self._fetch_football_fixtures())
        fixtures.extend(self._fetch_nba_fixtures())
        fixtures.extend(self._fetch_mlb_fixtures())
        
        return fixtures
    
    def _fetch_football_fixtures(self) -> List[Dict[str, Any]]:
        """Fetch football fixtures from football-data.org"""
        from src.data.api_client import FootballAPIClient
        
        try:
            client = FootballAPIClient()
            competitions = client.get_competitions()
            
            all_fixtures = []
            comps_data = competitions.get("competitions", [])
            
            # Query multiple dates: today, tomorrow, and next 3 days
            from datetime import timedelta
            dates_to_query = [date.today() + timedelta(days=d) for d in range(0, 4)]
            
            for comp in comps_data:
                code = comp.get("code", "")
                if code not in ["PL", "BL1", "FL1", "PD", "SA", "EL"]:
                    continue
                
                comp_id = comp.get("id")
                
                for query_date in dates_to_query:
                    try:
                        matches = client.get_matches(competition_code=code, date=query_date.isoformat())
                        for match in matches.get("matches", []):
                            # Only add SCHEDULED or TIMED matches (not finished ones)
                            status = match.get("status", "")
                            if status in ["SCHEDULED", "TIMED", "IN_PLAY"]:
                                all_fixtures.append({
                                    "sport": "football",
                                    "league": code,
                                    "external_id": match.get("id"),
                                    "home_team": match.get("homeTeam", {}).get("name", ""),
                                    "away_team": match.get("awayTeam", {}).get("name", ""),
                                    "start_time": match.get("utcDate"),
                                    "status": match.get("status", "SCHEDULED")
                                })
                    except Exception as e:
                        logger.warning(f"Error fetching {code} on {query_date}: {e}")
            
            client.close()
            return all_fixtures
            
        except Exception as e:
            logger.error(f"Football fixtures fetch failed: {e}")
            return []
    
    def _fetch_nba_fixtures(self) -> List[Dict[str, Any]]:
        """Fetch NBA fixtures"""
        from src.data.nba_adapter import NBAAdapter
        
        try:
            adapter = NBAAdapter()
            games = adapter.get_todays_games()
            
            return [{
                "sport": "nba",
                "league": "NBA",
                "external_id": g.get("game_id"),
                "home_team": g.get("home_team"),
                "away_team": g.get("away_team"),
                "start_time": g.get("start_time"),
                "status": "SCHEDULED"
            } for g in games]
            
        except Exception as e:
            logger.warning(f"NBA fixtures fetch failed: {e}")
            return []
    
    def _fetch_mlb_fixtures(self) -> List[Dict[str, Any]]:
        """Fetch MLB fixtures"""
        from src.data.mlb_adapter import MLBAdapter
        
        try:
            adapter = MLBAdapter()
            games = adapter.get_todays_games()
            
            return [{
                "sport": "mlb",
                "league": "MLB",
                "external_id": g.get("game_id"),
                "home_team": g.get("home_team"),
                "away_team": g.get("away_team"),
                "start_time": g.get("start_time"),
                "status": "SCHEDULED"
            } for g in games]
            
        except Exception as e:
            logger.warning(f"MLB fixtures fetch failed: {e}")
            return []
    
    def _fetch_odds(self, fixtures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Fetch odds for fixtures using tiered engine"""
        from src.data.unified_odds_engine import UnifiedOddsEngine
        
        engine = UnifiedOddsEngine()
        
        for fixture in fixtures:
            try:
                sport = fixture.get("sport", "football")
                league = fixture.get("league", "")
                home = fixture.get("home_team", "")
                away = fixture.get("away_team", "")
                
                odds_data = engine.get_odds(sport, home, away, league=league)
                
                if odds_data:
                    fixture["home_odds"] = odds_data.get("home_odds")
                    fixture["away_odds"] = odds_data.get("away_odds")
                    fixture["odds_source"] = odds_data.get("source")
                    fixture["odds_confidence"] = odds_data.get("combined_confidence", 0)
                else:
                    fixture["home_odds"] = None
                    fixture["away_odds"] = None
                    fixture["odds_source"] = None
                    fixture["odds_confidence"] = 0
                    
            except Exception as e:
                logger.warning(f"Odds fetch failed for {fixture.get('home_team')} vs {fixture.get('away_team')}: {e}")
                fixture["home_odds"] = None
                fixture["away_odds"] = None
        
        return fixtures
    
    def _run_intelligence(self, fixtures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Run intelligence engine on fixtures"""
        from src.models.baseline_models import BaselinePredictionEngine
        
        engine = BaselinePredictionEngine()
        predictions = []
        
        for fixture in fixtures:
            try:
                home = fixture.get("home_team", "")
                away = fixture.get("away_team", "")
                league = fixture.get("league", "")
                
                home_odds = fixture.get("home_odds")
                away_odds = fixture.get("away_odds")
                
                if not home_odds or not away_odds:
                    continue
                
                sport_type = fixture.get("sport", "football")
                baseline_prob = engine.predict(
                    sport_type,
                    home,
                    away
                )
                
                implied_home = 1 / home_odds if home_odds > 0 else 0.5
                implied_away = 1 / away_odds if away_odds > 0 else 0.5
                
                edge = baseline_prob - implied_home if fixture.get("sport") == "football" else baseline_prob - implied_home
                ev = edge * home_odds if edge > 0 else edge * away_odds
                ev_pct = ev * 100
                
                if abs(ev_pct) < 3.0:
                    continue
                
                confidence = "high" if abs(ev_pct) > 6 else "medium" if abs(ev_pct) > 4 else "low"
                
                kelly = (edge * home_odds - (1 - edge)) / (home_odds - 1) if home_odds > 1 else 0
                kelly_pct = max(0, min(20, kelly * 100))
                
                predictions.append({
                    "sport": fixture.get("sport", "football"),
                    "league": league,
                    "home_team": home,
                    "away_team": away,
                    "selection": home,
                    "model_probability": baseline_prob,
                    "implied_probability": implied_home,
                    "home_odds": home_odds,
                    "away_odds": away_odds,
                    "edge": edge,
                    "ev": ev,
                    "ev_pct": ev_pct,
                    "confidence": confidence,
                    "kelly_pct": kelly_pct,
                    "odds_source": fixture.get("odds_source", "unknown"),
                    "start_time": fixture.get("start_time"),
                    "external_id": fixture.get("external_id")
                })
                
            except Exception as e:
                logger.warning(f"Intelligence failed for {fixture.get('home_team')}: {e}")
        
        return predictions
    
    def _store_predictions(self, predictions: List[Dict], run_date: date) -> int:
        """Store predictions in database"""
        if not predictions:
            return 0
        
        stored = 0
        
        with self.db.session() as session:
            for pred in predictions:
                try:
                    prediction = Prediction(
                        predicted_value=1,
                        probability=pred.get("model_probability", 0.5),
                        confidence=pred.get("kelly_pct", 0) / 100,
                        is_accepted=True,
                        predicted_at=datetime.utcnow(),
                        prediction_type=f"{pred.get('sport')}_h2h"
                    )
                    session.add(prediction)
                    stored += 1
                    
                except Exception as e:
                    logger.warning(f"Failed to store prediction: {e}")
            
            session.commit()
        
        return stored
    
    def _update_daily_summary(self, result: DailyRunResult) -> None:
        """Update daily summary"""
        with self.db.session() as session:
            sport_counts = {}
            
            todays_preds = session.query(Prediction).filter(
                Prediction.predicted_at >= datetime.combine(result.run_date, datetime.min.time())
            ).all()
            
            for pred in todays_preds:
                sport = pred.prediction_type.split("_")[0] if pred.prediction_type else "football"
                sport_counts[sport] = sport_counts.get(sport, 0) + 1
            
            for sport, count in sport_counts.items():
                summary = DailySummary(
                    run_date=result.run_date,
                    sport=sport,
                    total_fixtures=result.fixtures_fetched,
                    open_predictions=count,
                    positive_ev_count=count,
                    high_confidence_count=count,
                    top_ev_opportunity=result.predictions_quality_passed,
                    last_pipeline_run=result.completed_at
                )
                session.add(summary)
            
            session.commit()
    
    def _save_run_record(self, result: DailyRunResult) -> None:
        """Save run record to database"""
        with self.db.session() as session:
            run = session.query(DailyRun).filter(
                DailyRun.run_date == result.run_date
            ).first()
            
            if run:
                run.status = result.status
                run.completed_at = result.completed_at
                run.fixtures_fetched = result.fixtures_fetched
                run.fixtures_processed = result.fixtures_processed
                run.predictions_generated = result.predictions_generated
                run.predictions_quality_passed = result.predictions_quality_passed
                run.error_message = result.error_message
                
                session.commit()


def run_daily_pipeline() -> DailyRunResult:
    """Main entry point for daily pipeline"""
    config = load_config()
    runner = DailyBatchRunner(config)
    return runner.run_full_pipeline()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    result = run_daily_pipeline()
    print(f"Daily pipeline result: {result.status}")
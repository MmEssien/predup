"""
Unified Daily Intelligence Runner
===================================
Uses:
- UnifiedOddsEngine (tiered priority: SportsGameOdds > OddsAPI > OddsPortal)
- BaselinePredictionEngine (simple math models for probability)
- Database-only storage (no JSON files)
"""

import sys
from pathlib import Path
_root = Path(r"C:\Users\Strategic Shelter\.antigravity\AI\PredUp")
sys.path.insert(0, str(_root))

import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
import os

env_file = _root / ".env"
if env_file.exists():
    load_dotenv(str(env_file))

# Debug: Print environment variables
print("DEBUG: ODDS_API_KEY set:", bool(os.getenv("ODDS_API_KEY")))
print("DEBUG: ODDS_API_KEY length:", len(os.getenv("ODDS_API_KEY") or ""))

logger = logging.getLogger(__name__)

# Database setup for standalone script
from src.data.database import (
    PredictionRecord, SportEvent, SportOdds, DailyRun, Base
)
from src.data.connection import DatabaseManager


class UnifiedIntelligenceEngine:
    """Unified Engine with tiered odds + baseline models - DB only storage"""
    
    def __init__(self):
        self.results = {
            "football": {"fixtures": 0, "predictions": [], "skipped": []},
            "mlb": {"fixtures": 0, "predictions": [], "skipped": []},
            "nba": {"fixtures": 0, "predictions": [], "skipped": []},
        }
        self.api_failures = {}
        self.total_fixtures = 0
        self.total_predictions = 0
        self.total_skipped = 0
        self.db_session = None
        self.daily_run = None
    
    def run(self, sports: List[str] = None):
        """Run unified intelligence across sports - DB only"""
        
        if sports is None:
            sports = ["football", "mlb", "nba"]
        
        print("=" * 70)
        print("  UNIFIED DAILY INTELLIGENCE")
        print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("=" * 70)
        
        # Initialize database
        db_manager = DatabaseManager.get_instance()
        self.db_session = db_manager.get_session()
        
        # Get or create daily run record for today
        existing = self.db_session.query(DailyRun).filter(
            DailyRun.run_date == date.today()
        ).first()
        
        if existing:
            self.daily_run = existing
            self.daily_run.status = "RUNNING"
            self.daily_run.started_at = datetime.utcnow()
            self.daily_run.completed_at = None
            self.daily_run.error_message = None
        else:
            self.daily_run = DailyRun(
                run_date=date.today(),
                status="RUNNING",
                started_at=datetime.utcnow()
            )
            self.db_session.add(self.daily_run)
        
        self.db_session.commit()
        
        try:
            # Initialize engines
            from src.data.unified_odds_engine import get_odds_engine
            from src.models.baseline_models import get_baseline_engine
            
            self.odds_engine = get_odds_engine()
            self.baseline = get_baseline_engine()
            
            for sport in sports:
                print(f"\n[{sport.upper()}]")
                self._process_sport(sport)
            
            # Close engines
            self.odds_engine.close()
            
            # Update daily run record
            self.daily_run.status = "COMPLETED"
            self.daily_run.completed_at = datetime.utcnow()
            self.daily_run.fixtures_fetched = self.total_fixtures
            self.daily_run.predictions_generated = self.total_predictions
            self.db_session.commit()
            
            # Print summary
            self._print_summary()
            
            print("\n" + self.odds_engine.get_daily_report())
            
        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            self.daily_run.status = "FAILED"
            self.daily_run.error_message = str(e)[:500]
            self.daily_run.completed_at = datetime.utcnow()
            self.db_session.commit()
            raise
        finally:
            self.db_session.close()
        
        return self.results
    
    def _process_sport(self, sport: str):
        """Process fixtures for a single sport - save to DB"""
        
        # Get fixtures from appropriate adapter
        fixtures = self._get_fixtures(sport)
        self.results[sport]["fixtures"] = len(fixtures)
        self.total_fixtures += len(fixtures)
        
        if not fixtures:
            print(f"  No fixtures (off-season or API issue)")
            return
        
        print(f"  Found {len(fixtures)} fixtures")
        
        # Process each fixture
        for fixture in fixtures:
            try:
                # Ensure fixture exists in SportEvent table (this extracts team names)
                sport_event = self._get_or_create_sport_event(fixture, sport)
                
                # Use the extracted team names from the SportEvent
                home = sport_event.home_team_name or ""
                away = sport_event.away_team_name or ""
                
                if not home or not away:
                    continue
                
                # Get baseline probability using string team names
                baseline_prob = self.baseline.predict(sport, home, away)
                
                # Get real odds from tiered engine
                odds_result = self.odds_engine.get_odds(sport, home, away)
                
                if not odds_result:
                    self.results[sport]["skipped"].append({
                        "home": home,
                        "away": away,
                        "reason": "no_odds"
                    })
                    self.total_skipped += 1
                    print(f"  SKIP: {home} vs {away} (no odds)")
                    continue
                
                # Calculate EV
                home_odds = odds_result.get("home_odds", 2.0)
                away_odds = odds_result.get("away_odds", 2.0)
                
                implied_home = 1 / home_odds
                implied_away = 1 / away_odds
                
                # Devig the market
                total_implied = implied_home + implied_away
                devig_home = implied_home / total_implied
                devig_away = implied_away / total_implied
                
                # Calculate edge and EV
                edge = baseline_prob - devig_home
                ev = baseline_prob * (home_odds - 1) - (1 - baseline_prob)
                
                # Decision
                decision = "no_bet"
                bet_on_home = None
                if baseline_prob > 0.5 and ev > 0.03:
                    decision = "bet_home"
                    bet_on_home = True
                elif baseline_prob < 0.5 and ev > 0.03:
                    decision = "bet_away"
                    bet_on_home = False
                
                # Save odds to SportOdds table
                self._save_odds_to_db(sport_event.id, sport, odds_result)
                
                if decision != "no_bet":
                    self.total_predictions += 1
                    
                    # Save prediction to PredictionRecord table
                    self._save_prediction_to_db(
                        sport_event=sport_event,
                        sport=sport,
                        baseline_prob=baseline_prob,
                        bet_on_home=bet_on_home,
                        home_odds=home_odds,
                        away_odds=away_odds,
                        devig_home=devig_home,
                        devig_away=devig_away,
                        edge=edge,
                        ev=ev,
                        odds_result=odds_result
                    )
                    
                    prediction = {
                        "sport": sport,
                        "fixture": f"{home} vs {away}",
                        "home_team": home,
                        "away_team": away,
                        "bet_on": "home" if bet_on_home else "away",
                        "baseline_prob": baseline_prob,
                        "odds": home_odds if bet_on_home else away_odds,
                        "implied_prob": devig_home if bet_on_home else devig_away,
                        "edge": edge,
                        "ev": ev,
                        "ev_pct": ev * 100,
                        "confidence": "medium",
                        "odds_source": odds_result.get("source", "unknown"),
                        "start_time": fixture.get("start_time", ""),
                        "league": fixture.get("league", sport.upper())
                    }
                    self.results[sport]["predictions"].append(prediction)
                    print(f"  BET: {home} vs {away} | Prob: {baseline_prob:.1%} | "
                          f"Odds: {home_odds:.2f} | EV: {ev*100:+.1f}% | Source: {odds_result.get('source')}")
                
            except Exception as e:
                logger.error(f"Error processing {sport} fixture: {e}")
                self.db_session.rollback()
        
        print(f"  Predictions: {len(self.results[sport]['predictions'])}")
    
    def _get_or_create_sport_event(self, fixture: dict, sport: str) -> SportEvent:
        """Get or create SportEvent record"""
        external_id = str(fixture.get("fixture_id", ""))
        
        # Extract team names (handle both strings and dicts from APIs)
        home_team = fixture.get("home_team", "")
        away_team = fixture.get("away_team", "")
        if isinstance(home_team, dict):
            home_team = home_team.get("name", "")
        if isinstance(away_team, dict):
            away_team = away_team.get("name", "")
        
        # Parse start_time to datetime if it's a string
        start_time = fixture.get("start_time")
        if isinstance(start_time, str):
            try:
                # Handle ISO format with Z suffix
                start_time = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            except:
                start_time = None
        
        # Check if exists
        event = self.db_session.query(SportEvent).filter(
            SportEvent.external_event_id == external_id,
            SportEvent.sport == sport
        ).first()
        
        if event:
            # Update if needed
            event.home_team_name = home_team or event.home_team_name
            event.away_team_name = away_team or event.away_team_name
            if start_time:
                event.start_time = start_time
            event.league = fixture.get("league", event.league)
            event.status = fixture.get("status", event.status)
            self.db_session.commit()
            return event
        
        # Create new (use extracted team names)
        event = SportEvent(
            sport=sport,
            league=fixture.get("league", sport.upper()),
            external_event_id=external_id,
            home_team_name=home_team,
            away_team_name=away_team,
            start_time=start_time,
            status=fixture.get("status", "SCHEDULED")
        )
        self.db_session.add(event)
        self.db_session.commit()
        return event
    
    def _save_odds_to_db(self, sport_event_id: int, sport: str, odds_result: dict):
        """Save odds to SportOdds table"""
        # Check if odds already exist for this event and bookmaker
        existing = self.db_session.query(SportOdds).filter(
            SportOdds.sport_event_id == sport_event_id,
            SportOdds.bookmaker == odds_result.get("source", "unknown")
        ).first()
        
        if existing:
            # Update existing
            existing.odds_decimal = odds_result.get("home_odds")
            existing.implied_probability = 1 / odds_result.get("home_odds", 2.0) if odds_result.get("home_odds") else None
            existing.timestamp = datetime.utcnow()
            self.db_session.commit()
            return
        
        # Create new odds record for home
        odds = SportOdds(
            sport_event_id=sport_event_id,
            sport=sport,
            market="h2h",
            bookmaker=odds_result.get("source", "unknown"),
            selection_name="home",
            odds_decimal=odds_result.get("home_odds"),
            implied_probability=1 / odds_result.get("home_odds", 2.0) if odds_result.get("home_odds") else None,
            timestamp=datetime.utcnow()
        )
        self.db_session.add(odds)
        
        # Create away odds record
        away_odds = SportOdds(
            sport_event_id=sport_event_id,
            sport=sport,
            market="h2h",
            bookmaker=odds_result.get("source", "unknown"),
            selection_name="away",
            odds_decimal=odds_result.get("away_odds"),
            implied_probability=1 / odds_result.get("away_odds", 2.0) if odds_result.get("away_odds") else None,
            timestamp=datetime.utcnow()
        )
        self.db_session.add(away_odds)
        self.db_session.commit()
    
    def _save_prediction_to_db(
        self,
        sport_event: SportEvent,
        sport: str,
        baseline_prob: float,
        bet_on_home: bool,
        home_odds: float,
        away_odds: float,
        devig_home: float,
        devig_away: float,
        edge: float,
        ev: float,
        odds_result: dict
    ):
        """Save prediction to PredictionRecord table"""
        # Check if prediction already exists
        existing = self.db_session.query(PredictionRecord).filter(
            PredictionRecord.fixture_id == sport_event.id,
            PredictionRecord.prediction_type == "home_win" if bet_on_home else "away_win"
        ).first()
        
        if existing:
            print(f"    Prediction already exists for {sport_event.home_team_name} vs {sport_event.away_team_name}")
            return
        
        # Determine predicted odds and implied prob
        predicted_odds = home_odds if bet_on_home else away_odds
        implied_prob = devig_home if bet_on_home else devig_away
        clv = baseline_prob - implied_prob
        
        prediction = PredictionRecord(
            fixture_id=sport_event.id,
            predicted_probability=baseline_prob,
            predicted_odds=predicted_odds,
            prediction_type="home_win" if bet_on_home else "away_win",
            market_odds_at_prediction=predicted_odds,
            market_bookmaker=odds_result.get("source", "unknown"),
            implied_probability=implied_prob,
            clv=clv,
            clv_percentage=clv * 100,
            edge_score=edge,
            is_accepted=True,
            predicted_at=datetime.utcnow()
        )
        self.db_session.add(prediction)
        self.db_session.commit()
    
    def _get_fixtures(self, sport: str) -> List[Dict]:
        """Get fixtures for sport"""
        if sport == "football":
            return self._get_football_fixtures()
        elif sport == "mlb":
            return self._get_mlb_fixtures()
        elif sport == "nba":
            return self._get_nba_fixtures()
        return []
    
    def _get_football_fixtures(self) -> List[Dict]:
        """Get football fixtures using football-data.org (API-Football free plan limited to 2022-2024)"""
        try:
            from src.data.api_client import FootballAPIClient
            
            client = FootballAPIClient()
            fixtures = []
            
            # Query multiple dates: today + next 7 days
            for i in range(8):
                query_date = (datetime.now() + timedelta(days=i)).strftime("%Y-%m-%d")
                try:
                    data = client.get_matches(date=query_date)
                    if not data or "matches" not in data:
                        continue
                    
                    for m in data.get("matches", []):
                        status = m.get("status", "")
                        # Include SCHEDULED, TIMED, IN_PLAY, and recent FINISHED for display
                        if status not in ["SCHEDULED", "TIMED", "IN_PLAY", "FINISHED"]:
                            continue
                        
                        home_team = m.get("homeTeam", {}).get("name", "")
                        away_team = m.get("awayTeam", {}).get("name", "")
                        league_code = m.get("competition", {}).get("code", "")
                        
                        if home_team and away_team:
                            fixtures.append({
                                "home_team": home_team,
                                "away_team": away_team,
                                "fixture_id": str(m.get("id")),
                                "start_time": m.get("utcDate"),
                                "league": league_code,
                                "status": status
                            })
                except Exception as e:
                    print(f"  Error fetching {query_date}: {e}")
                    continue
            
            client.close()
            
            if not fixtures:
                print(f"  No fixtures found (may be off-season)")
            else:
                scheduled = [f for f in fixtures if f.get("status") in ["SCHEDULED", "TIMED", "IN_PLAY"]]
                finished = [f for f in fixtures if f.get("status") == "FINISHED"]
                print(f"  Found {len(fixtures)} fixtures ({len(scheduled)} upcoming, {len(finished)} finished)")
            
            return fixtures
        except Exception as e:
            self.api_failures["football"] = str(e)
            print(f"  Football-Data.org error: {e}")
            return []
    
    def _get_mlb_fixtures(self) -> List[Dict]:
        """Get MLB fixtures using ESPN (FREE, real-time 2026)"""
        try:
            from src.data.espn_adapter import ESPNAdapter
            
            adapter = ESPNAdapter()
            games = adapter.get_mlb_fixtures(days_ahead=3)
            adapter.close()
            
            if not games:
                print(f"  No MLB fixtures found (ESPN)")
                return []
            
            print(f"  Found {len(games)} MLB fixtures (ESPN, 2026)")
            
            return [{
                "home_team": g.get("home_team", ""),
                "away_team": g.get("away_team", ""),
                "fixture_id": str(g.get("fixture_id", "")),
                "start_time": g.get("start_time"),
                "league": "MLB"
            } for g in games if g.get("home_team")]
        except Exception as e:
            self.api_failures["mlb"] = str(e)
            print(f"  MLB error: {e}")
            return []
    
    def _get_nba_fixtures(self) -> List[Dict]:
        """Get NBA fixtures using ESPN (FREE, real-time 2026)"""
        try:
            from src.data.espn_adapter import ESPNAdapter
            
            adapter = ESPNAdapter()
            games = adapter.get_nba_fixtures(days_ahead=3)
            adapter.close()
            
            if not games:
                print(f"  No NBA fixtures found (ESPN)")
                return []
            
            print(f"  Found {len(games)} NBA fixtures (ESPN, 2026)")
            
            return [{
                "home_team": g.get("home_team", ""),
                "away_team": g.get("away_team", ""),
                "fixture_id": str(g.get("fixture_id", "")),
                "start_time": g.get("start_time"),
                "league": "NBA"
            } for g in games if g.get("home_team")]
        except Exception as e:
            self.api_failures["nba"] = str(e)
            print(f"  NBA error: {e}")
            return []
            
            return [{
                "home_team": g.get("home_team"),
                "away_team": g.get("away_team"),
                "fixture_id": str(g.get("fixture_id")),
                "start_time": g.get("start_time"),
                "league": "NBA"
            } for g in games if g.get("home_team")]
        except Exception as e:
            self.api_failures["nba"] = str(e)
            return []
    
    def _print_summary(self):
        """Print operational summary"""
        print("\n" + "=" * 70)
        print("  OPERATIONAL TRUTH CHECKS")
        print("=" * 70)
        
        print(f"\nFixtures Found: {self.total_fixtures}")
        print(f"Predictions Made: {self.total_predictions}")
        print(f"Skipped (no odds): {self.total_skipped}")
        
        if self.api_failures:
            print(f"\nAPI Failures:")
            for sport, error in self.api_failures.items():
                print(f"  {sport}: {error[:60]}")
        
        # Top opportunities
        print("\n" + "=" * 70)
        print("  TOP OPPORTUNITIES")
        print("=" * 70)
        
        all_preds = []
        for sport, data in self.results.items():
            for pred in data["predictions"]:
                pred["_sport"] = sport
                all_preds.append(pred)
        
        if not all_preds:
            print("  No betting opportunities found")
            return
        
        all_preds.sort(key=lambda x: x.get("ev_pct",0), reverse=True)
        
        for i, p in enumerate(all_preds[:10], 1):
            sport = p.get("_sport", "").upper()
            home = p.get("home_team", "?")
            away = p.get("away_team", "?")
            bet = p.get("bet_on", "?")
            prob = p.get("baseline_prob", 0)
            odds = p.get("odds", 0)
            ev = p.get("ev_pct", 0)
            
            print(f"{i:2}. [{sport:6}] {home} vs {away}")
            print(f"        Bet: {bet:4} | Prob: {prob:.1%} | Odds: {odds:.2f} | EV: {ev:+.1f}%")
    
    def _save(self):
        """DEPRECATED - Now using DB-only storage"""
        print("\n[DEPRECATED] JSON storage removed - using database only")
        pass
    
    def _save(self):
        """Save predictions to JSON and Database"""
        all_preds = []
        
        for sport, data in self.results.items():
            for pred in data["predictions"]:
                pred["sport"] = sport
                pred["created_at"] = datetime.now().isoformat()
                pred["status"] = "pending"
                all_preds.append(pred)
        
        if not all_preds:
            print("\nNo predictions to save")
            return
        
        # Save to JSON for history
        output_file = _root / "data" / f"daily_predictions_{datetime.now().strftime('%Y-%m-%d')}.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, "w") as f:
            json.dump({
                "run_at": datetime.now().isoformat(),
                "total_predictions": len(all_preds),
                "predictions": all_preds,
            }, f, indent=2, default=str)
            
        print(f"\nSaved {len(all_preds)} predictions to {output_file.name}")

        # Save to Database
        try:
            from src.data.database import SessionLocal, Prediction, Fixture, Team
            from sqlalchemy import func
            db = SessionLocal()
            
            saved_count = 0
            for p in all_preds:
                # Find fixture by joining through Team table
                home_name = p.get("home_team", "")
                away_name = p.get("away_team", "")
                
                HomeTeam = db.query(Team).filter(
                    func.lower(Team.name) == home_name.lower()
                ).first()
                AwayTeam = db.query(Team).filter(
                    func.lower(Team.name) == away_name.lower()
                ).first()
                
                fixture = None
                if HomeTeam and AwayTeam:
                    fixture = db.query(Fixture).filter(
                        Fixture.home_team_id == HomeTeam.id,
                        Fixture.away_team_id == AwayTeam.id,
                        Fixture.status == "SCHEDULED"
                    ).first()
                
                if fixture:
                    # Check if prediction already exists
                    existing = db.query(Prediction).filter(
                        Prediction.fixture_id == fixture.id,
                        Prediction.prediction_type == "h2h"
                    ).first()
                    
                    if not existing:
                        db_pred = Prediction(
                            fixture_id=fixture.id,
                            prediction_type="h2h",
                            predicted_value=1.0 if p["bet_on"] == "home" else 2.0,
                            probability=p["baseline_prob"],
                            confidence=0.7,
                            predicted_at=datetime.now()
                        )
                        db.add(db_pred)
                        saved_count += 1
                else:
                    logger.warning(f"No fixture match for {home_name} vs {away_name}")
            
            db.commit()
            db.close()
            print(f"Persisted {saved_count} predictions to the database")
        except Exception as e:
            print(f"Error persisting to database: {e}")


def main():
    """Main entry point"""
    engine = UnifiedIntelligenceEngine()
    engine.run()


if __name__ == "__main__":
    main()
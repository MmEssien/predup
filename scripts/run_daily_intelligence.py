"""
Unified Daily Intelligence Runner
===================================
Uses:
- UnifiedOddsEngine (tiered priority: SportsGameOdds > OddsAPI > OddsPortal)
- BaselinePredictionEngine (simple math models for probability)
- No simulation in production
"""

import sys
from pathlib import Path
_root = Path(r"C:\Users\Strategic Shelter\.antigravity\AI\PredUp")
sys.path.insert(0, str(_root))

import logging
from datetime import datetime
from typing import Dict, List
from dotenv import load_dotenv
import json

load_dotenv(_root / ".env")
logger = logging.getLogger(__name__)


class UnifiedIntelligenceEngine:
    """Unified Engine with tiered odds + baseline models"""
    
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
    
    def run(self, sports: List[str] = None):
        """Run unified intelligence across sports"""
        
        if sports is None:
            sports = ["football", "mlb", "nba"]
        
        print("=" * 70)
        print("  UNIFIED DAILY INTELLIGENCE")
        print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("=" * 70)
        
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
        
        # Print summary
        self._print_summary()
        
        # Save predictions
        self._save()
        
        print("\n" + self.odds_engine.get_daily_report())
        
        return self.results
    
    def _process_sport(self, sport: str):
        """Process fixtures for a single sport"""
        
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
                home = fixture.get("home_team", "")
                away = fixture.get("away_team", "")
                
                if not home or not away:
                    continue
                
                # Get baseline probability
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
                
                # Calculate edge
                edge = baseline_prob - devig_home
                ev = baseline_prob * (home_odds - 1) - (1 - baseline_prob)
                
                # Decision
                decision = "no_bet"
                if baseline_prob > 0.5 and ev > 0.03:
                    decision = "bet_home"
                elif baseline_prob < 0.5 and ev > 0.03:
                    decision = "bet_away"
                
                if decision != "no_bet":
                    self.total_predictions += 1
                    prediction = {
                        "sport": sport,
                        "fixture": f"{home} vs {away}",
                        "home_team": home,
                        "away_team": away,
                        "bet_on": "home" if decision == "bet_home" else "away",
                        "baseline_prob": baseline_prob,
                        "odds": home_odds if decision == "bet_home" else away_odds,
                        "implied_prob": devig_home if decision == "bet_home" else (1-devig_home),
                        "edge": edge,
                        "ev": ev,
                        "ev_pct": ev * 100,
                        "confidence": "medium",
                        "odds_source": odds_result.get("source", "unknown"),
                        "start_time": fixture.get("start_time", ""),
                        "league": sport.upper()
                    }
                    self.results[sport]["predictions"].append(prediction)
                    print(f"  BET: {home} vs {away} | Prob: {baseline_prob:.1%} | "
                          f"Odds: {home_odds:.2f} | EV: {ev*100:+.1f}% | Source: {odds_result.get('source')}")
                
            except Exception as e:
                logger.error(f"Error processing {sport} fixture: {e}")
        
        print(f"  Predictions: {len(self.results[sport]['predictions'])}")
    
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
        """Get football fixtures"""
        try:
            from src.data.api_football_client import ApiFootballClient
            
            client = ApiFootballClient("")
            today = datetime.now().strftime("%Y-%m-%d")
            data = client.get_fixtures(date=today)
            client.close()
            
            fixtures = []
            for f in data.get("response", []):
                teams = f.get("teams", {})
                home = teams.get("home", {})
                away = teams.get("away", {})
                
                if home.get("name") and away.get("name"):
                    fixtures.append({
                        "home_team": home.get("name"),
                        "away_team": away.get("name"),
                        "fixture_id": str(f.get("id")),
                        "start_time": f.get("date"),
                        "league": f.get("league", {}).get("name", "")
                    })
            
            return fixtures
        except Exception as e:
            self.api_failures["football"] = str(e)
            return []
    
    def _get_mlb_fixtures(self) -> List[Dict]:
        """Get MLB fixtures"""
        try:
            from src.data.mlb_adapter import MLBAdapter
            
            adapter = MLBAdapter()
            games = adapter.get_fixtures(days_ahead=3)
            adapter.close()
            
            return [{
                "home_team": g.get("home_team"),
                "away_team": g.get("away_team"),
                "fixture_id": str(g.get("game_id")),
                "start_time": g.get("game_datetime"),
                "league": "MLB"
            } for g in games if g.get("home_team")]
        except Exception as e:
            self.api_failures["mlb"] = str(e)
            return []
    
    def _get_nba_fixtures(self) -> List[Dict]:
        """Get NBA fixtures"""
        try:
            from src.data.nba_adapter import NBAAdapter
            
            adapter = NBAAdapter()
            games = adapter.get_fixtures(days_ahead=3)
            adapter.close()
            
            if not games:
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
        
        all_preds.sort(key=lambda x: x.get("ev_pct", 0), reverse=True)
        
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
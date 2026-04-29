"""
MLB Shadow Mode Tracker
Tracks predictions vs actual outcomes for model validation
"""

import sys
from pathlib import Path
_root = Path(r"C:\Users\Strategic Shelter\.antigravity\AI\PredUp")
sys.path.insert(0, str(_root))

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dotenv import load_dotenv
import numpy as np

load_dotenv(_root / ".env")
logger = logging.getLogger(__name__)


class ShadowModeTracker:
    """Track shadow mode predictions and outcomes"""
    
    def __init__(self, storage_path: str = None):
        self.storage_path = storage_path or str(_root / "data" / "shadow_mode.json")
        Path(self.storage_path).parent.mkdir(parents=True, exist_ok=True)
        self.predictions = []
        self.load()
    
    def load(self):
        """Load existing predictions"""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r") as f:
                    data = json.load(f)
                    self.predictions = data.get("predictions", [])
                    logger.info(f"Loaded {len(self.predictions)} predictions")
            except Exception as e:
                logger.error(f"Load error: {e}")
    
    def save(self):
        """Save predictions"""
        try:
            with open(self.storage_path, "w") as f:
                json.dump({
                    "predictions": self.predictions,
                    "updated": datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Save error: {e}")
    
    def add_prediction(self, prediction: Dict):
        """Add a new prediction"""
        prediction["created_at"] = datetime.now().isoformat()
        prediction["status"] = "pending"
        self.predictions.append(prediction)
        self.save()
    
    def add_outcome(self, game_id: str, actual_win: int):
        """Add outcome for a prediction"""
        for p in self.predictions:
            if p.get("game_id") == game_id and p.get("status") == "pending":
                p["actual_win"] = actual_win
                p["status"] = "completed"
                p["won"] = (p["bet_on"] == actual_win)
                p["completed_at"] = datetime.now().isoformat()
                
                # Calculate profit
                odds = p["odds"]
                if p["won"]:
                    if odds >= 1:
                        p["profit"] = odds - 1
                    else:
                        p["profit"] = (1 / odds) - 1
                else:
                    p["profit"] = -1
                
                self.save()
                break
    
    def get_summary(self) -> Dict:
        """Get summary statistics"""
        completed = [p for p in self.predictions if p.get("status") == "completed"]
        
        if not completed:
            return {
                "total_predictions": len(self.predictions),
                "completed": 0,
                "pending": sum(1 for p in self.predictions if p.get("status") == "pending")
            }
        
        n = len(completed)
        wins = sum(1 for p in completed if p.get("won"))
        total_profit = sum(p.get("profit", 0) for p in completed)
        expected_ev = sum(p.get("ev_pct", 0) for p in completed) / n
        actual_roi = (total_profit / n) * 100 if n > 0 else 0
        
        return {
            "total_predictions": len(self.predictions),
            "completed": n,
            "pending": sum(1 for p in self.predictions if p.get("status") == "pending"),
            "wins": wins,
            "losses": n - wins,
            "win_rate": wins / n * 100 if n > 0 else 0,
            "total_profit": total_profit,
            "avg_profit": total_profit / n if n > 0 else 0,
            "expected_roi": expected_ev,
            "actual_roi": actual_roi,
            "roi_gap": expected_ev - actual_roi,
            "avg_ev": expected_ev,
            "bets_per_day": n / max(1, self._days_tracked())
        }
    
    def _days_tracked(self) -> int:
        """Get number of days tracked"""
        if not self.predictions:
            return 1
        dates = set(p.get("created_at", "")[:10] for p in self.predictions if p.get("created_at"))
        return max(1, len(dates))
    
    def get_detailed_results(self) -> Dict:
        """Get detailed results for analysis"""
        completed = [p for p in self.predictions if p.get("status") == "completed"]
        
        if not completed:
            return {}
        
        # Sort by date
        completed.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
        # EV bucket analysis
        buckets = {}
        for p in completed:
            ev_bucket = int(p.get("ev_pct", 0) // 10) * 10
            bucket_key = f"{ev_bucket}-{ev_bucket+10}%"
            if bucket_key not in buckets:
                buckets[bucket_key] = {"n": 0, "wins": 0, "profit": 0, "ev": 0}
            
            buckets[bucket_key]["n"] += 1
            buckets[bucket_key]["ev"] += p.get("ev_pct", 0)
            if p.get("won"):
                buckets[bucket_key]["wins"] += 1
            buckets[bucket_key]["profit"] += p.get("profit", 0)
        
        # Calculate ROI per bucket
        for bucket in buckets.values():
            bucket["roi"] = (bucket["profit"] / bucket["n"] * 100) if bucket["n"] > 0 else 0
            bucket["win_rate"] = (bucket["wins"] / bucket["n"] * 100) if bucket["n"] > 0 else 0
            bucket["avg_ev"] = bucket["ev"] / bucket["n"] if bucket["n"] > 0 else 0
        
        return {
            "recent_predictions": completed[:20],
            "buckets": buckets
        }


def run_shadow_mode():
    """Run shadow mode for current games"""
    
    print("="*70)
    print("  MLB SHADOW MODE TRACKER")
    print("="*70)
    
    tracker = ShadowModeTracker()
    summary = tracker.get_summary()
    
    print("\n[1] Summary")
    print(f"    Total predictions: {summary['total_predictions']}")
    print(f"    Completed: {summary['completed']}")
    print(f"    Pending: {summary['pending']}")
    
    if summary["completed"] > 0:
        print(f"\n[2] Performance")
        print(f"    Win rate: {summary['win_rate']:.1f}%")
        print(f"    Total profit: ${summary['total_profit']:.2f}")
        print(f"    Expected ROI: {summary['expected_roi']:+.1f}%")
        print(f"    Actual ROI: {summary['actual_roi']:+.1f}%")
        print(f"    ROI gap: {summary['roi_gap']:+.1f}%")
        
        # EV bucket analysis
        print("\n[3] EV Bucket Performance")
        results = tracker.get_detailed_results()
        if results.get("buckets"):
            for bucket, data in results["buckets"].items():
                print(f"    {bucket}: n={data['n']}, win={data['win_rate']:.0f}%, "
                      f"ROI={data['roi']:+.1f}%, EV={data['avg_ev']:+.1f}%")
        
        # Recent predictions
        print("\n[4] Recent Predictions")
        for p in results.get("recent_predictions", [])[:5]:
            bet = "WIN" if p.get("won") else "LOSS"
            print(f"    {p.get('home')} vs {p.get('away')}: {bet} (${p.get('profit', 0):+.2f})")
    else:
        print("\n    No completed predictions yet")
        print("    Run with live odds to track shadow mode")
    
    return tracker


def create_daily_prediction_script():
    """Create script that can be scheduled daily"""
    
    script = '''"""
MLB Daily Shadow Mode Predictions
Run this daily to generate and track shadow mode predictions
"""
import sys
from pathlib import Path
_root = Path(__file__).parent.parent
sys.path.insert(0, str(_root))

import numpy as np
from scripts.mlb_xgboost_model import generate_realistic_dataset, train_xgboost_model
from scripts.live_betting_pipeline import run_live_predictions
from scripts.shadow_mode_tracker import ShadowModeTracker

def daily_predictions():
    print("="*70)
    print("  DAILY MLB PREDICTIONS")
    print("="*70)
    
    # Load or train model
    from sklearn.linear_model import LogisticRegression
    from sklearn.calibration import CalibratedClassifierCV
    import xgboost as xgb
    
    # Load data
    df = generate_realistic_dataset(2000)
    
    # Train model
    X = df.drop(["home_win", "true_prob"], axis=1).values
    y = df["home_win"].values
    
    model = xgb.XGBClassifier(n_estimators=100, max_depth=4, learning_rate=0.1)
    calibrated = CalibratedClassifierCV(model, method="isotonic", cv=5)
    calibrated.fit(X, y)
    
    # Get live odds
    from src.intelligence.the_odds_api import TheOddsAPIProvider
    the_odds = TheOddsAPIProvider()
    odds_data = the_odds.get_odds("baseball_mlb", "us")
    
    if not odds_data.get("data"):
        print("No games found")
        return
    
    games = odds_data["data"]
    tracker = ShadowModeTracker()
    
    print(f"\\nProcessing {len(games)} games...")
    
    for game in games:
        home = game.get("home_team")
        away = game.get("away_team")
        
        # Generate features (replace with real StatsAPI data)
        features = np.array([[
            np.random.normal(4.0, 1.0),  # ERA
            np.random.normal(4.0, 1.0),
            1.35, 1.35,  # WHIP
            0.20, 0.20,  # K rate
            np.random.normal(0.750, 0.080),
            np.random.normal(0.750, 0.080),
            0, 0,  # Run diff
            np.random.choice([0, 1, 2]),
            np.random.choice([0, 1, 2]),
            np.random.uniform(0.3, 0.7),
            np.random.uniform(0.3, 0.7),
            0.4, 0.4,  # Bullpen
            1  # Home advantage
        ]])
        
        prob = calibrated.predict_proba(features)[0, 1]
        
        # Get odds
        bookmakers = game.get("bookmakers", [])
        if bookmakers:
            bm = bookmakers[0]
            for market in bm.get("markets", []):
                if market.get("key") == "h2h":
                    home_odds = None
                    for o in market.get("outcomes", []):
                        if o.get("name") == home:
                            home_odds = o.get("price")
                    
                    if home_odds:
                        implied = 1 / home_odds
                        ev = prob * (home_odds - 1) - (1 - prob)
                        ev_pct = ev * 100
                        
                        # Only track qualifying bets
                        if ev_pct >= 5.0:
                            tracker.add_prediction({
                                "game_id": f"{home}_vs_{away}",
                                "home": home,
                                "away": away,
                                "prob": prob,
                                "implied": implied,
                                "odds": home_odds,
                                "ev_pct": ev_pct,
                                "bet_on": 1  # Bet on home team
                            })
    
    the_odds.close()
    
    # Show summary
    run_shadow_mode()

if __name__ == "__main__":
    daily_predictions()
'''
    
    script_path = _root / "scripts" / "daily_mlb_predictions.py"
    with open(script_path, "w") as f:
        f.write(script)
    
    print(f"\\nDaily prediction script created: {script_path}")
    print("Run daily with: python scripts/daily_mlb_predictions.py")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Show current summary
    run_shadow_mode()
    
    # Option to create daily script
    create_daily_prediction_script()
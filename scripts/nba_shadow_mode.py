"""
NBA Shadow Mode Tracker
Paper trading mode to validate NBA predictions before going live
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


class NBAShadowTracker:
    """Track NBA shadow mode predictions and outcomes"""
    
    def __init__(self, storage_path: str = None):
        self.storage_path = storage_path or str(_root / "data" / "nba_shadow_mode.json")
        Path(self.storage_path).parent.mkdir(parents=True, exist_ok=True)
        self.predictions = []
        self.load()
    
    def load(self):
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r") as f:
                    data = json.load(f)
                    self.predictions = data.get("predictions", [])
                    logger.info(f"Loaded {len(self.predictions)} NBA predictions")
            except Exception as e:
                logger.error(f"Load error: {e}")
    
    def save(self):
        try:
            with open(self.storage_path, "w") as f:
                json.dump({
                    "predictions": self.predictions,
                    "updated": datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Save error: {e}")
    
    def add_prediction(
        self,
        game_id: str,
        home_team: str,
        away_team: str,
        bet_on: str,
        model_prob: float,
        odds: float,
        ev_pct: float,
        edge: float,
        market: str = "moneyline"
    ):
        """Add a new NBA prediction"""
        prediction = {
            "sport": "nba",
            "game_id": game_id,
            "home_team": home_team,
            "away_team": away_team,
            "bet_on": bet_on,
            "model_prob": model_prob,
            "odds": odds,
            "ev_pct": ev_pct,
            "edge": edge,
            "market": market,
            "created_at": datetime.now().isoformat(),
            "status": "pending"
        }
        self.predictions.append(prediction)
        self.save()
        logger.info(f"Added NBA prediction: {home_team} vs {away_team}, bet={bet_on}, prob={model_prob:.2f}")
    
    def add_outcome(self, game_id: str, actual_home_win: bool):
        """Add outcome for a prediction"""
        for p in self.predictions:
            if p.get("game_id") == game_id and p.get("status") == "pending":
                actual_win = 1 if actual_home_win else 0
                actual_bet_won = (p["bet_on"] == "home" and actual_home_win) or (p["bet_on"] == "away" and not actual_home_win)
                
                p["actual_win"] = actual_win
                p["status"] = "completed"
                p["won"] = actual_bet_won
                p["completed_at"] = datetime.now().isoformat()
                
                odds = p["odds"]
                if actual_bet_won:
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
                "sport": "nba",
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
            "sport": "nba",
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
        if not self.predictions:
            return 1
        dates = set(p.get("created_at", "")[:10] for p in self.predictions if p.get("created_at"))
        return max(1, len(dates))
    
    def get_detailed_results(self) -> Dict:
        completed = [p for p in self.predictions if p.get("status") == "completed"]
        
        if not completed:
            return {}
        
        completed.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
        buckets = {}
        for p in completed:
            ev_bucket = int(p.get("ev_pct", 0) // 10) * 10
            bucket_key = f"{ev_bucket}-{ev_bucket+10}%"
            if bucket_key not in buckets:
                buckets[bucket_key] = {"n": 0, "wins": 0, "profit": 0, "ev": 0}
            
            buckets[bucket_key]["n"] += 1
            if p.get("won"):
                buckets[bucket_key]["wins"] += 1
            buckets[bucket_key]["profit"] += p.get("profit", 0)
            buckets[bucket_key]["ev"] += p.get("ev_pct", 0)
        
        for b in buckets:
            n = buckets[b]["n"]
            if n > 0:
                buckets[b]["win_rate"] = buckets[b]["wins"] / n * 100
                buckets[b]["roi"] = buckets[b]["profit"] / n * 100
                buckets[b]["avg_ev"] = buckets[b]["ev"] / n
        
        return {
            "completed": completed,
            "recent_predictions": completed[:10],
            "buckets": buckets
        }
    
    def should_activate(self, min_bets: int = 30, min_roi: float = 2.0) -> Dict:
        """Check if should move from shadow to live"""
        summary = self.get_summary()
        
        if summary["completed"] < min_bets:
            return {"ready": False, "reason": f"Insufficient bets: {summary['completed']}/{min_bets}"}
        
        if summary["actual_roi"] < min_roi:
            return {"ready": False, "reason": f"ROI below threshold: {summary['actual_roi']:.1f}% < {min_roi}%"}
        
        if abs(summary["roi_gap"]) > 10:
            return {"ready": False, "reason": f"Poor calibration: gap={summary['roi_gap']:.1f}%"}
        
        return {
            "ready": True,
            "reason": "All criteria met",
            "summary": summary
        }


def run_nba_shadow_mode():
    """Run NBA shadow mode display"""
    
    print("="*70)
    print("  NBA SHADOW MODE TRACKER")
    print("="*70)
    
    tracker = NBAShadowTracker()
    summary = tracker.get_summary()
    
    print(f"\n[1] Summary")
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
        
        print("\n[3] EV Bucket Performance")
        results = tracker.get_detailed_results()
        if results.get("buckets"):
            for bucket, data in results["buckets"].items():
                print(f"    {bucket}: n={data['n']}, win={data.get('win_rate',0):.0f}%, "
                      f"ROI={data.get('roi',0):+.1f}%, EV={data.get('avg_ev',0):+.1f}%")
        
        print("\n[4] Activation Check")
        activation = tracker.should_activate()
        if activation["ready"]:
            print(f"    READY TO GO LIVE!")
        else:
            print(f"    Not ready: {activation['reason']}")
    else:
        print("\n    No completed predictions yet")
        print("    Run prediction script to start tracking")
    
    return tracker


if __name__ == "__main__":
    run_nba_shadow_mode()
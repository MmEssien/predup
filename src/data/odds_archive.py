"""
Odds Archive
===========
Stores historical odds snapshots for:
- Line movement tracking
- CLV analysis
- Model training data
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

CACHE_DIR = Path(".cache")
ARCHIVE_DIR = CACHE_DIR / "odds_archive"
ARCHIVE_DIR.mkdir(exist_ok=True, parents=True)


class OddsArchive:
    """
    Archive all odds pulls for analysis.
    """
    
    def __init__(self):
        self.today = datetime.now().strftime("%Y-%m-%d")
        self.archive_file = ARCHIVE_DIR / f"odds_{self.today}.jsonl"
    
    def save(self, odds_data: Dict) -> None:
        """Save odds snapshot to archive"""
        if not odds_data:
            return
        
        record = {
            "timestamp": datetime.now().isoformat(),
            "sport": odds_data.get("sport"),
            "home_team": odds_data.get("home_team"),
            "away_team": odds_data.get("away_team"),
            "league": odds_data.get("league"),
            "home_odds": odds_data.get("home_odds"),
            "away_odds": odds_data.get("away_odds"),
            "source": odds_data.get("source"),
            "confidence": odds_data.get("combined_confidence"),
        }
        
        with open(self.archive_file, "a") as f:
            f.write(json.dumps(record) + "\n")
    
    def get_history(
        self,
        home_team: str,
        away_team: str = None,
        days: int = 7
    ) -> List[Dict]:
        """Get odds history for a team/match"""
        history = []
        
        # Read last N days
        for i in range(days):
            date = datetime.now()
            date = date.replace(day=date.day - i)
            date_str = date.strftime("%Y-%m-%d")
            
            file = ARCHIVE_DIR / f"odds_{date_str}.jsonl"
            if not file.exists():
                continue
            
            with open(file, "r") as f:
                for line in f:
                    try:
                        record = json.loads(line)
                        if home_team.lower() in record.get("home_team", "").lower():
                            if away_team is None or away_team.lower() in record.get("away_team", "").lower():
                                history.append(record)
                    except:
                        continue
        
        return history
    
    def get_line_movement(
        self,
        home_team: str,
        away_team: str,
        days: int = 1
    ) -> Optional[Dict]:
        """Calculate line movement"""
        history = self.get_history(home_team, away_team, days=days)
        
        if len(history) < 2:
            return None
        
        # Get first and last odds
        first = history[0]
        last = history[-1]
        
        home_move = None
        away_move = None
        
        if first.get("home_odds") and last.get("home_odds"):
            home_move = last["home_odds"] - first["home_odds"]
        
        if first.get("away_odds") and last.get("away_odds"):
            away_move = last["away_odds"] - first["away_odds"]
        
        return {
            "home_team": home_team,
            "away_team": away_team,
            "home_move": home_move,
            "away_move": away_move,
            "snapshots": len(history)
        }


# Global instance
_archive = None

def get_odds_archive() -> OddsArchive:
    global _archive
    if _archive is None:
        _archive = OddsArchive()
    return _archive
"""Script to cleanup stale data and maintain database integrity"""

import os
import sys
from datetime import datetime, timedelta

# Add parent directory to path to allow imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.data.connection import DatabaseManager
from src.data.database import Fixture, Prediction, OddsData

def cleanup_stale_data():
    db_manager = DatabaseManager.get_instance()
    
    with db_manager.session() as session:
        now = datetime.utcnow()
        yesterday = now - timedelta(days=1)
        stale_threshold = now - timedelta(days=7)
        
        print(f"Starting data cleanup at {now}...")
        
        # 1. Archive/Delete fixtures from yesterday that were cancelled or postponed
        stale_fixtures = session.query(Fixture).filter(
            Fixture.utc_date < yesterday,
            Fixture.status.in_(["CANCELLED", "POSTPONED", "TIMELINE_NOT_AVAILABLE"])
        ).delete()
        print(f"Deleted {stale_fixtures} stale/cancelled fixtures.")
        
        # 2. Delete test/sample rows (ID > 1000000 or similar if applicable)
        # For now, let's just delete fixtures with no teams
        phantom_fixtures = session.query(Fixture).filter(
            (Fixture.home_team_id == None) | (Fixture.away_team_id == None)
        ).delete()
        print(f"Deleted {phantom_fixtures} phantom fixtures (missing teams).")
        
        # 3. Mark yesterday's predictions as settled if they are still 'active' but match is finished
        
        # 4. Cleanup old odds data to save space
        old_odds = session.query(OddsData).filter(
            OddsData.fetched_at < stale_threshold
        ).delete()
        print(f"Deleted {old_odds} old odds records.")
        
        session.commit()
        print("Cleanup complete.")

if __name__ == "__main__":
    cleanup_stale_data()

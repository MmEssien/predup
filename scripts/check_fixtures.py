"""Check what fixtures we have in the database"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from src.data.connection import DatabaseManager
from src.data.database import Fixture, Competition
from sqlalchemy import select, and_
from datetime import datetime, timedelta

db_manager = DatabaseManager.get_instance()
db_manager.initialize()

with db_manager.session() as session:
    # Check fixtures in next 7 days
    future = datetime.utcnow() + timedelta(days=7)
    now = datetime.utcnow()
    
    stmt = select(Fixture).where(
        and_(
            Fixture.utc_date >= now,
            Fixture.utc_date <= future
        )
    ).order_by(Fixture.utc_date)
    
    fixtures = session.execute(stmt).scalars().all()
    
    print(f"Found {len(fixtures)} upcoming fixtures in database:")
    
    for f in fixtures[:20]:
        print(f"  {f.utc_date.strftime('%Y-%m-%d %H:%M')} | CompID:{f.competition_id} | {f.home_team_id} vs {f.away_team_id}")
    
    # Also check total fixtures by status
    from sqlalchemy import func
    stmt_count = select(Fixture.status, func.count(Fixture.id)).group_by(Fixture.status)
    
    print("\nBy status:")
    for row in session.execute(stmt_count).all():
        print(f"  {row[0]}: {row[1]} fixtures")
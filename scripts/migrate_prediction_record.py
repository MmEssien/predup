"""Migrate database to latest schema.

Run this once to update the database schema.
"""
import sys
from pathlib import Path

_root = Path(__file__).parent.parent
sys.path.insert(0, str(_root))

from dotenv import load_dotenv
load_dotenv(_root / ".env")

from src.data.connection import DatabaseManager
from src.data.database import Base

def migrate():
    # Initialize database connection
    db = DatabaseManager.get_instance()
    db.initialize()
    engine = db.engine
    
    print(f"Database dialect: {engine.dialect.name}")
    print("Creating all tables...")
    
    # Create all tables defined in Base.metadata
    Base.metadata.create_all(engine)
    
    print("Migration complete!")
    print("All tables created including: sport_events, prediction_records, daily_runs")

if __name__ == "__main__":
    migrate()

"""Migrate PredictionRecord to reference sport_events

Run this once to update the database schema.
WARNING: This will drop and recreate the prediction_records table.
"""
import sys
from pathlib import Path

_root = Path(__file__).parent.parent
sys.path.insert(0, str(_root))

from dotenv import load_dotenv
load_dotenv(_root / ".env")

from src.data.connection import DatabaseManager
from src.data.database import Base, PredictionRecord
from sqlalchemy import inspect

def migrate():
    db = DatabaseManager.get_instance()
    engine = db.engine
    
    inspector = inspect(engine)
    
    # Check if prediction_records table exists
    if 'prediction_records' in inspector.get_table_names():
        print("Dropping existing prediction_records table...")
        with engine.connect() as conn:
            # Drop with CASCADE to remove foreign key constraints
            if engine.dialect.name == 'postgresql':
                conn.execute("DROP TABLE IF EXISTS prediction_records CASCADE")
            else:
                # SQLite doesn't support DROP TABLE IF EXISTS with CASCADE
                conn.execute("DROP TABLE IF EXISTS prediction_records")
            conn.commit()
        print("Table dropped.")
    
    # Recreate the table with new schema
    print("Creating prediction_records table with new schema...")
    Base.metadata.create_all(engine, tables=[PredictionRecord.__table__])
    print("Migration complete!")
    print("NOTE: The fixture_id column now references sport_events.id")

if __name__ == "__main__":
    migrate()

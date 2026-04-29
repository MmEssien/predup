"""
Database Migration Script - Add Intelligence Tables

Creates new tables for CLV tracking, odds history, and market signals.

Usage:
    python scripts/migrate_intelligence_tables.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import inspect
from src.data.connection import DatabaseManager
from src.data.database import Base

# Import models to register them
from src.data.database import PredictionRecord, OddsHistory, MarketSignal


def main():
    print("="*50)
    print("  DATABASE MIGRATION - Intelligence Tables")
    print("="*50)
    
    db_manager = DatabaseManager.get_instance()
    db_manager.initialize()
    
    # Get existing tables
    inspector = inspect(db_manager.engine)
    existing = set(inspector.get_table_names())
    
    print(f"\nExisting tables: {len(existing)}")
    
    # These are the new tables
    new_tables = ['prediction_records', 'odds_history', 'market_signals']
    
    # Check what needs to be created
    to_create = [t for t in new_tables if t not in existing]
    
    print(f"\nNew tables to create: {to_create}")
    
    if to_create:
        print("\nCreating tables...")
        # Use create_all which only creates missing tables
        Base.metadata.create_all(db_manager.engine)
        print("Done!")
    else:
        print("\nAll tables already exist!")
    
    # Verify
    inspector = inspect(db_manager.engine)
    final_tables = set(inspector.get_table_names())
    
    print("\n" + "-"*50)
    print("Verification:")
    for table in new_tables:
        status = "OK" if table in final_tables else "MISSING"
        print(f"  {table}: {status}")
    
    if all(t in final_tables for t in new_tables):
        print("\n[MIGRATION COMPLETE]")
    else:
        print("\n[WARNING] Some tables missing - check logs]")


if __name__ == "__main__":
    main()
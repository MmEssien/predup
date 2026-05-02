"""Test database tables"""
import sys
from pathlib import Path

# Add project root to path
_root = Path(__file__).parent
sys.path.insert(0, str(_root))

from src.data.connection import DatabaseManager
from sqlalchemy import inspect

# Initialize database
db = DatabaseManager.get_instance()
db.initialize()

# Get table names
inspector = inspect(db.engine)
tables = inspector.get_table_names()

print("Tables in database:")
for t in sorted(tables):
    print(f"  - {t}")
print(f"\nTotal: {len(tables)} tables")

# Test query on SportEvent
from src.data.database import SportEvent
with db.session() as session:
    count = session.query(SportEvent).count()
    print(f"\nSportEvent count: {count}")

db.close()

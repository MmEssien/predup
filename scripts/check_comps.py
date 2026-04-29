"""Check available competition IDs in database"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from src.data.connection import DatabaseManager
from src.data.database import Competition
from sqlalchemy import select

db_manager = DatabaseManager.get_instance()
db_manager.initialize()

with db_manager.session() as session:
    comps = session.execute(select(Competition)).scalars().all()
    
    print("Available Competitions:")
    for c in comps:
        print(f"  ID:{c.id} | ext:{c.external_id} | {c.name} ({c.code})")
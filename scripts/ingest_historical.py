"""Historical data ingestion script - Simple version"""

import sys
import logging
import os
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from src.data.pipeline import DataPipeline
from src.data.connection import DatabaseManager
from src.data.repositories import FixtureRepository, TeamRepository, CompetitionRepository
from src.data.database import Fixture, Team
from src.utils.helpers import load_config, ensure_dir
import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PRIORITY_COMPETITIONS = [
    # Current seasons (already have these)
    ("PL", 2024),
    ("PL", 2023),
    ("BL1", 2024),
    ("BL1", 2023),
    ("PD", 2024),
    ("PD", 2023),
    ("SA", 2024),
    ("SA", 2023),
    ("FL1", 2024),
    ("FL1", 2023),
    # Phase 3: Add 2022 season
    ("PL", 2022),
    ("BL1", 2022),
    ("PD", 2022),
    ("SA", 2022),
    ("FL1", 2022),
]


def save_to_database(df, session) -> int:
    """Save fetched matches to database"""
    if df.empty:
        return 0
    
    saved = 0
    for _, row in df.iterrows():
        try:
            # Get or create competition
            comp_code = row.get("competition")
            comp = session.query(Team).first()  # Just to test
            
            # Get teams - try to find by external_id
            home_ext = row.get("home_team_id")
            away_ext = row.get("away_team_id")
            
            if pd.isna(home_ext) or pd.isna(away_ext):
                continue
                
            home_ext = int(float(home_ext))
            away_ext = int(float(away_ext))
            
            # Get or create home team
            home_team = session.query(Team).filter(Team.external_id == home_ext).first()
            if not home_team:
                home_team = Team(
                    external_id=home_ext,
                    name=str(row.get("home_team_name", ""))
                )
                session.add(home_team)
                session.flush()
            
            # Get or create away team
            away_team = session.query(Team).filter(Team.external_id == away_ext).first()
            if not away_team:
                away_team = Team(
                    external_id=away_ext,
                    name=str(row.get("away_team_name", ""))
                )
                session.add(away_team)
                session.flush()
            
            # Create fixture
            from src.data.database import Competition
            comp = session.query(Competition).filter(Competition.code == comp_code).first()
            comp_id = comp.id if comp else None
            
            fixture = session.query(Fixture).filter(Fixture.external_id == int(row["match_id"])).first()
            if not fixture:
                fixture = Fixture(
                    external_id=int(row["match_id"]),
                    competition_id=comp_id,
                    season=row.get("season"),
                    utc_date=row["date"],
                    status=row.get("status", "FINISHED"),
                    home_team_id=home_team.id,
                    away_team_id=away_team.id,
                    home_score=int(row["home_score"]) if pd.notna(row.get("home_score")) else None,
                    away_score=int(row["away_score"]) if pd.notna(row.get("away_score")) else None,
                    winner=row.get("winner"),
                )
                session.add(fixture)
                saved += 1
                
        except Exception as e:
            logger.debug(f"Error: {e}")
    
    return saved


def main():
    config = load_config()
    ensure_dir("data/raw")
    
    db_manager = DatabaseManager.get_instance()
    db_manager.initialize()
    
    pipeline = DataPipeline()
    
    logger.info("=" * 50)
    logger.info("Historical Data Ingestion")
    logger.info("=" * 50)
    
    total_saved = 0
    
    for comp_code, season in PRIORITY_COMPETITIONS:
        csv_path = f"data/raw/{comp_code}_{season}.csv"
        
        if os.path.exists(csv_path):
            logger.info(f"\nUsing cached: {comp_code} {season}")
            df = pd.read_csv(csv_path)
        else:
            logger.info(f"\nFetching: {comp_code} {season}")
            try:
                df = pipeline.fetch_historical_matches(
                    competition_code=comp_code,
                    season=season,
                    save_path=csv_path
                )
            except Exception as e:
                logger.error(f"Error: {e}")
                continue
        
        if df.empty:
            continue
            
        with db_manager.session() as session:
            saved = save_to_database(df, session)
            total_saved += saved
            logger.info(f"  Saved {saved} matches")
    
    pipeline.close()
    
    logger.info("\n" + "=" * 50)
    logger.info(f"Total saved: {total_saved} matches")


if __name__ == "__main__":
    main()
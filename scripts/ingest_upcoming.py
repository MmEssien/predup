"""
Ingest upcoming fixtures from API-Football for production leagues
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from src.data.connection import DatabaseManager
from src.data.api_football_client import ApiFootballClient
from src.data.database import Fixture, Competition, Team
from sqlalchemy import select
from datetime import datetime, timedelta

db_manager = DatabaseManager.get_instance()
db_manager.initialize()

api_client = ApiFootballClient()

# League configs
LEAGUE_MAP = {
    7: "BL1",   # Bundesliga
    3: "PL",    # Premier League
}

print("=== Ingesting upcoming fixtures ===\n")

now = datetime.utcnow()
future = now + timedelta(days=7)

for comp_id, league_code in LEAGUE_MAP.items():
    print(f"Fetching {league_code} (comp_id: {comp_id})...")
    
    try:
        response = api_client.client.get(
            f"{api_client.base_url}/fixtures",
            params={
                "league": comp_id,
                "from": now.strftime("%Y-%m-%d"),
                "to": future.strftime("%Y-%m-%d"),
                "status": "NS"  # Not Started
            }
        )
        response.raise_for_status()
        data = response.json()
        
        fixtures = data.get("response", [])
        print(f"  Found {len(fixtures)} fixtures")
        
        with db_manager.session() as session:
            for f in fixtures:
                fixture_data = f["fixture"]
                teams = f["teams"]
                
                # Get or create teams
                home_ext_id = teams["home"]["id"]
                away_ext_id = teams["away"]["id"]
                
                # Check if team exists
                home_team = session.execute(
                    select(Team).where(Team.external_id == home_ext_id)
                ).scalar_one_or_none()
                
                if not home_team:
                    home_team = Team(
                        external_id=home_ext_id,
                        name=teams["home"]["name"],
                        short_name=teams["home"]["name"][:3].upper()
                    )
                    session.add(home_team)
                    session.flush()
                
                away_team = session.execute(
                    select(Team).where(Team.external_id == away_ext_id)
                ).scalar_one_or_none()
                
                if not away_team:
                    away_team = Team(
                        external_id=away_ext_id,
                        name=teams["away"]["name"],
                        short_name=teams["away"]["name"][:3].upper()
                    )
                    session.add(away_team)
                    session.flush()
                
                # Check if fixture exists
                existing = session.execute(
                    select(Fixture).where(Fixture.external_id == fixture_data["id"])
                ).scalar_one_or_none()
                
                if not existing:
                    fixture = Fixture(
                        external_id=fixture_data["id"],
                        competition_id=comp_id,
                        season=2024,
                        utc_date=datetime.fromisoformat(fixture_data["date"].replace("Z", "+00:00")),
                        status=fixture_data["status"]["short"],
                        home_team_id=home_team.id,
                        away_team_id=away_team.id,
                        venue=fixture_data.get("venue", {}).get("name")
                    )
                    session.add(fixture)
                    
        session.commit()
        print(f"  Saved {len(fixtures)} fixtures to database")
        
    except Exception as e:
        print(f"  Error: {e}")

api_client.close()

# Verify
with db_manager.session() as session:
    upcoming = session.execute(
        select(Fixture).where(
            Fixture.utc_date >= now
        ).order_by(Fixture.utc_date)
    ).scalars().all()
    
    print(f"\nTotal upcoming: {len(upcoming)}")
    for f in upcoming:
        print(f"  {f.utc_date.strftime('%Y-%m-%d %H:%M')} | CompID:{f.competition_id}")

print("\n[COMPLETE]")
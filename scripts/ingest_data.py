"""Data ingestion script - loads all data into database"""

import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

from src.data.unified_client import get_unified_client
from src.data.connection import get_db_context
from src.data.repositories import (
    TeamRepository, CompetitionRepository, FixtureRepository,
    WeatherRepository, OddsRepository
)
from src.data.pipeline import DataPipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def ingest_competitions(client) -> None:
    """Ingest competitions from football-data.org"""
    logger.info("Ingesting competitions...")
    competitions = client.get_competitions()

    with get_db_context() as session:
        repo = CompetitionRepository(session)
        for comp in competitions:
            if comp.get("code"):
                repo.upsert(
                    external_id=comp["id"],
                    data={
                        "external_id": comp["id"],
                        "name": comp.get("name"),
                        "code": comp.get("code"),
                        "area_name": comp.get("area", {}).get("name"),
                        "emblem_url": comp.get("emblem")
                    }
                )
        logger.info(f"Ingested {len(competitions)} competitions")


def ingest_fixtures(days_ahead: int = 7) -> pd.DataFrame:
    """Ingest upcoming fixtures"""
    logger.info(f"Ingesting fixtures for next {days_ahead} days...")
    pipeline = DataPipeline()
    matches = pipeline.fetch_upcoming_matches(days_ahead=days_ahead)

    if matches.empty:
        logger.warning("No fixtures fetched")
        return matches

    with get_db_context() as session:
        team_repo = TeamRepository(session)
        comp_repo = CompetitionRepository(session)
        fixture_repo = FixtureRepository(session)

        for _, match in matches.iterrows():
            comp_code = match.get("competition_code")
            if comp_code:
                comp = comp_repo.get_by_code(comp_code)
                comp_id = comp.id if comp else None
            else:
                comp_id = None

            for team_name, team_id_key in [
                (match["home_team_name"], "home_team_id"),
                (match["away_team_name"], "away_team_id")
            ]:
                if pd.notna(team_name):
                    ext_id = match.get(team_id_key)
                    if ext_id:
                        team_repo.upsert(
                            external_id=int(ext_id),
                            data={
                                "external_id": int(ext_id),
                                "name": team_name
                            }
                        )

            fixture_repo.upsert(
                external_id=match["match_id"],
                data={
                    "external_id": match["match_id"],
                    "competition_id": comp_id,
                    "season": datetime.now().year,
                    "utc_date": match["date"],
                    "status": match.get("status", "SCHEDULED"),
                    "home_team_id": team_repo.get_by_external_id(int(match["home_team_id"])).id if pd.notna(match.get("home_team_id")) else None,
                    "away_team_id": team_repo.get_by_external_id(int(match["away_team_id"])).id if pd.notna(match.get("away_team_id")) else None,
                    "venue": match.get("venue")
                }
            )

        logger.info(f"Ingested {len(matches)} fixtures")

    pipeline.close()
    return matches


def ingest_weather(fixtures_df: pd.DataFrame) -> None:
    """Ingest weather data for fixtures"""
    logger.info("Ingesting weather data...")
    pipeline = DataPipeline()
    venues = pipeline.fetch_team_venues()

    weather_data = pipeline.fetch_weather_for_matches(fixtures_df, venues)

    with get_db_context() as session:
        weather_repo = WeatherRepository(session)
        fixture_repo = FixtureRepository(session)

        for _, w in weather_data.iterrows():
            fixture = fixture_repo.get_by_external_id(w["match_id"])
            if fixture:
                weather_repo.upsert(
                    fixture_id=fixture.id,
                    data={
                        "latitude": w.get("latitude", 0),
                        "longitude": w.get("longitude", 0),
                        "temperature_max": w.get("temperature_max"),
                        "temperature_min": w.get("temperature_min"),
                        "precipitation_prob": w.get("precipitation_prob"),
                        "weather_code": w.get("weather_code")
                    }
                )

    logger.info(f"Ingested weather for {len(weather_data)} matches")
    pipeline.close()


def ingest_odds(sport: str = "soccer_england_premier_league") -> None:
    """Ingest odds data from the-odds-api.com"""
    logger.info(f"Ingesting odds for {sport}...")
    pipeline = DataPipeline()
    odds_data = pipeline.fetch_odds(sport)

    if not odds_data or "data" not in odds_data:
        logger.warning("No odds data fetched")
        pipeline.close()
        return

    with get_db_context() as session:
        odds_repo = OddsRepository(session)
        fixture_repo = FixtureRepository(session)

        count = 0
        for event in odds_data.get("data", []):
            home_team = event.get("home_team", "")
            away_team = event.get("away_team", "")
            commence_time = event.get("commence_time", "")

            for bookmaker in event.get("bookmakers", []):
                bk_name = bookmaker.get("title")
                for market in bookmaker.get("markets", []):
                    if market.get("key") == "h2h":
                        outcomes = market.get("outcomes", [])
                        home_odds = away_odds = draw_odds = None

                        for outcome in outcomes:
                            name = outcome.get("name", "").lower()
                            od = outcome.get("price")
                            if "home" in name or home_team.lower() in name:
                                home_odds = od
                            elif "away" in name or away_team.lower() in name:
                                away_odds = od
                            elif "draw" in name:
                                draw_odds = od

                        if home_odds and away_odds:
                            total = home_odds + away_odds + (draw_odds or 0)
                            home_prob = (1 / home_odds / total * 100) if total > 0 else None
                            away_prob = (1 / away_odds / total * 100) if total > 0 else None
                            draw_prob = (1 / draw_odds / total * 100) if draw_odds and total > 0 else None

                            odds_repo.upsert(
                                fixture_id=None,
                                bookmaker=bk_name,
                                data={
                                    "external_fixture_key": event.get("id"),
                                    "sport": sport,
                                    "home_odds": home_odds,
                                    "draw_odds": draw_odds,
                                    "away_odds": away_odds,
                                    "home_prob": home_prob,
                                    "away_prob": away_prob,
                                    "draw_prob": draw_prob,
                                    "market_type": "h2h"
                                }
                            )
                            count += 1

        logger.info(f"Ingested {count} odds entries")

    pipeline.close()


def main():
    logger.info("Starting data ingestion...")

    client = get_unified_client()

    try:
        ingest_competitions(client)
        fixtures = ingest_fixtures(days_ahead=7)

        if not fixtures.empty:
            ingest_weather(fixtures)

        ingest_odds()

        logger.info("Data ingestion complete!")

    except Exception as e:
        logger.error(f"Data ingestion failed: {e}")
        raise
    finally:
        client.close()


if __name__ == "__main__":
    main()
"""Data pipeline for PredUp"""

import logging
import os
from typing import Optional, Dict, List
import pandas as pd
from datetime import datetime, timedelta

# Ensure environment is loaded
from dotenv import load_dotenv
load_dotenv()

from src.data.unified_client import get_unified_client, UnifiedAPIClient

logger = logging.getLogger(__name__)


class DataPipeline:
    """Data ingestion pipeline"""

    def __init__(self, client: Optional[UnifiedAPIClient] = None):
        self.client = client or get_unified_client()

    def fetch_historical_matches(
        self,
        competition_code: str,
        season: int,
        save_path: Optional[str] = None
    ) -> pd.DataFrame:
        """Fetch historical match data for a competition/season"""
        logger.info(f"Fetching {competition_code} season {season}")

        data = self.client.football_data.get_competition_matches(competition_code, season)
        matches = data.get("matches", [])

        records = []
        for match in matches:
            records.append({
                "match_id": match.get("id"),
                "competition": competition_code,
                "season": season,
                "date": match.get("utcDate"),
                "status": match.get("status"),
                "home_team_id": match.get("homeTeam", {}).get("id"),
                "home_team_name": match.get("homeTeam", {}).get("name"),
                "away_team_id": match.get("awayTeam", {}).get("id"),
                "away_team_name": match.get("awayTeam", {}).get("name"),
                "home_score": match.get("score", {}).get("fullTime", {}).get("home"),
                "away_score": match.get("score", {}).get("fullTime", {}).get("away"),
                "winner": match.get("score", {}).get("winner"),
            })

        df = pd.DataFrame(records)
        df["date"] = pd.to_datetime(df["date"])

        if save_path:
            df.to_csv(save_path, index=False)
            logger.info(f"Saved {len(df)} matches to {save_path}")

        return df

    def fetch_upcoming_matches(
        self,
        days_ahead: int = 7,
        save_path: Optional[str] = None
    ) -> pd.DataFrame:
        """Fetch upcoming matches from all competitions"""
        logger.info(f"Fetching upcoming matches for next {days_ahead} days")

        matches = self.client.get_upcoming_fixtures(days_ahead=days_ahead)

        records = []
        for match in matches:
            records.append({
                "match_id": match.get("id"),
                "competition": match.get("competition", {}).get("name"),
                "competition_code": match.get("competition", {}).get("code"),
                "date": match.get("utcDate"),
                "status": match.get("status"),
                "home_team_id": match.get("homeTeam", {}).get("id"),
                "home_team_name": match.get("homeTeam", {}).get("name"),
                "away_team_id": match.get("awayTeam", {}).get("id"),
                "away_team_name": match.get("awayTeam", {}).get("name"),
                "venue": match.get("venue"),
            })

        df = pd.DataFrame(records)
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])

        if save_path:
            df.to_csv(save_path, index=False)
            logger.info(f"Saved {len(df)} upcoming matches to {save_path}")

        return df

    def fetch_team_venues(self) -> Dict[int, tuple]:
        """Fetch team venue coordinates for weather data"""
        return self.client.get_team_venues()

    def fetch_weather_for_matches(self, matches: pd.DataFrame, venues: Dict[int, tuple]) -> pd.DataFrame:
        """Fetch weather data for upcoming matches"""
        weather_records = []

        for _, match in matches.iterrows():
            match_date = match["date"].strftime("%Y-%m-%d") if isinstance(match["date"], datetime) else str(match["date"])[:10]
            home_team_id = match.get("home_team_id")

            if home_team_id and home_team_id in venues:
                lat, lon = venues[home_team_id]
                weather = self.client.get_weather_for_fixture(lat, lon, match_date)

                if weather:
                    weather_records.append({
                        "match_id": match["match_id"],
                        "date": match_date,
                        **weather
                    })

        return pd.DataFrame(weather_records)

    def fetch_odds(self, sport: str = "soccer_england_premier_league") -> Dict:
        """Fetch odds data from the-odds-api.com"""
        logger.info(f"Fetching odds for {sport}")
        credits_left = self.client.check_odds_credits()
        if credits_left is not None:
            logger.info(f"Odds API credits remaining: {credits_left}")

        return self.client.get_odds_for_matches(sport=sport)

    def close(self):
        self.client.close()
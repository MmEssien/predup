"""Unified API Client Facade - Abstracts multiple data sources"""

import os
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from src.data.api_client import FootballAPIClient
from src.data.api_football_client import ApiFootballClient
from src.data.weather_client import WeatherAPIClient
from src.data.odds_client import OddsAPIClient

logger = logging.getLogger(__name__)


class UnifiedAPIClient:
    """Unified interface for all data providers"""

    def __init__(self):
        self.football_data = FootballAPIClient(
            api_key=os.getenv("FOOTBALL_DATA_KEY"),
            base_url=os.getenv("FOOTBALL_DATA_URL", "https://api.football-data-org/v4")
        )
        self.api_football = ApiFootballClient(
            api_key=os.getenv("API_FOOTBALL_COM_KEY"),
            base_url=os.getenv("API_FOOTBALL_COM_URL", "https://v3.football.api-sports.io")
        )
        self.weather = WeatherAPIClient(
            base_url=os.getenv("WEATHER_API_BASE_URL", "https://api.open-meteo.com/v1")
        )
        self.odds = OddsAPIClient(
            api_key=os.getenv("ODDS_API_KEY")
        )
        logger.info("Unified API Client initialized")

    def get_competitions(self) -> List[Dict]:
        """Get available competitions from football-data.org"""
        data = self.football_data.get_competitions()
        if isinstance(data, list):
            return data
        return data.get("competitions", [])

    def get_upcoming_fixtures(self, days_ahead: int = 7) -> List[Dict]:
        """Get upcoming fixtures for major leagues"""
        fixtures = []
        today = datetime.now().date()

        for i in range(days_ahead):
            date = today + timedelta(days=i)
            date_str = date.isoformat()
            try:
                data = self.football_data.get_matches_by_date(date_str)
                fixtures.extend(data.get("matches", []))
            except Exception as e:
                logger.warning(f"Failed to fetch fixtures for {date_str}: {e}")

        return fixtures

    def get_team_venues(self) -> Dict[int, tuple]:
        """Get team venues with coordinates for weather data"""
        venue_coords = {}
        premier_league_id = 2021
        try:
            data = self.api_football.get_teams(league_id=premier_league_id, season=2024)
            for team in data.get("response", []):
                team_id = team["team"]["id"]
                venue = team["team"].get("venue", {})
                if venue.get("latitude") and venue.get("longitude"):
                    venue_coords[team_id] = (
                        float(venue["latitude"]),
                        float(venue["longitude"])
                    )
        except Exception as e:
            logger.warning(f"Failed to fetch team venues: {e}")
        return venue_coords

    def get_weather_for_fixture(self, latitude: float, longitude: float, date: str) -> Optional[Dict]:
        """Get weather forecast for fixture date/location"""
        try:
            forecast = self.weather.get_forecast(latitude, longitude)
            daily = forecast.get("daily", {})
            dates = daily.get("time", [])

            if date in dates:
                idx = dates.index(date)
                return {
                    "temperature_max": daily.get("temperature_2m_max", [None])[idx],
                    "temperature_min": daily.get("temperature_2m_min", [None])[idx],
                    "precipitation_prob": daily.get("precipitation_probability_max", [None])[idx],
                    "weather_code": daily.get("weather_code", [None])[idx],
                }
        except Exception as e:
            logger.warning(f"Failed to fetch weather: {e}")
        return None

    def get_odds_for_matches(self, sport: str = "soccer_england_premier_league") -> Dict:
        """Get current odds for matches"""
        return self.odds.get_odds(sport=sport)

    def check_odds_credits(self) -> Optional[int]:
        """Check remaining odds API credits"""
        return self.odds.get_credits_remaining()

    def close(self):
        self.football_data.close()
        self.api_football.close()
        self.weather.close()
        self.odds.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


_client: Optional[UnifiedAPIClient] = None


def get_unified_client() -> UnifiedAPIClient:
    global _client
    if _client is None:
        _client = UnifiedAPIClient()
    return _client
"""Weather API Client using Open-Meteo (free, no API key required)"""

import os
from typing import Optional
import httpx
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class WeatherAPIClient:
    """Client for Open-Meteo weather API"""

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or os.getenv(
            "WEATHER_API_BASE_URL",
            "https://api.open-meteo.com/v1"
        )
        self.timeout = 15
        self._client: Optional[httpx.Client] = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def close(self):
        if self._client:
            self._client.close()
            self._client = None

    def get_forecast(self, latitude: float, longitude: float) -> dict:
        """Fetch weather forecast for coordinates"""
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,weather_code,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "timezone": "auto",
            "forecast_days": 7
        }
        response = self.client.get(f"{self.base_url}/forecast", params=params)
        response.raise_for_status()
        return response.json()

    def get_historical(self, latitude: float, longitude: float, date: str) -> dict:
        """Fetch historical weather for a specific date (YYYY-MM-DD)"""
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": date,
            "end_date": date,
            "hourly": "temperature_2m,weather_code,wind_speed_10m",
            "timezone": "auto"
        }
        response = self.client.get(f"{self.base_url}/forecast", params=params)
        response.raise_for_status()
        return response.json()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
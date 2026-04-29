"""API Client for api-football.com"""

import os
from typing import Optional
import httpx
import logging

logger = logging.getLogger(__name__)


class ApiFootballClient:
    """Client for api-football.com"""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or os.getenv("API_FOOTBALL_COM_KEY")
        self.base_url = base_url or os.getenv(
            "API_FOOTBALL_COM_URL",
            "https://v3.football.api-sports.io"
        )
        self.timeout = 30
        self._client: Optional[httpx.Client] = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                headers={
                    "x-apisports-key": self.api_key,
                    "Content-Type": "application/json"
                },
                timeout=self.timeout
            )
        return self._client

    def close(self):
        if self._client:
            self._client.close()
            self._client = None

    def get_leagues(self) -> dict:
        """Fetch available leagues"""
        response = self.client.get(f"{self.base_url}/leagues")
        response.raise_for_status()
        return response.json()

    def get_fixtures(self, date: Optional[str] = None, league_id: Optional[int] = None) -> dict:
        """Fetch fixtures by date or league"""
        params = {}
        if date:
            params["date"] = date
        if league_id:
            params["league"] = league_id
        response = self.client.get(f"{self.base_url}/fixtures", params=params)
        response.raise_for_status()
        return response.json()

    def get_fixture(self, fixture_id: int) -> dict:
        """Fetch specific fixture details"""
        response = self.client.get(f"{self.base_url}/fixtures", params={"id": fixture_id})
        response.raise_for_status()
        return response.json()

    def get_teams(self, league_id: int, season: int) -> dict:
        """Fetch teams for a league/season"""
        response = self.client.get(
            f"{self.base_url}/teams",
            params={"league": league_id, "season": season}
        )
        response.raise_for_status()
        return response.json()

    def get_team(self, team_id: int) -> dict:
        """Fetch team details"""
        response = self.client.get(f"{self.base_url}/teams", params={"id": team_id})
        response.raise_for_status()
        return response.json()

    def get_statistics(self, fixture_id: int, team_id: int) -> dict:
        """Fetch fixture statistics for a team"""
        response = self.client.get(
            f"{self.base_url}/fixtures/statistics",
            params={"fixture": fixture_id, "team": team_id}
        )
        response.raise_for_status()
        return response.json()

    def get_odds(self, league_id: Optional[int] = None, date: Optional[str] = None) -> dict:
        """Fetch odds data"""
        params = {}
        if league_id:
            params["league"] = league_id
        if date:
            params["date"] = date
        response = self.client.get(f"{self.base_url}/odds", params=params)
        response.raise_for_status()
        return response.json()

    def get_fixture_odds(self, fixture_id: int) -> Optional[dict]:
        """Get odds for specific fixture with bookmaker details"""
        try:
            response = self.client.get(
                f"{self.base_url}/odds",
                params={"fixture": fixture_id}
            )
            response.raise_for_status()
            data = response.json()
            
            if not data.get("results", 0) > 0:
                return None
            
            # Get first bookmaker's odds
            bookmaker_data = data.get("response", [{}])[0]
            bookmaker = bookmaker_data.get("bookmaker", {})
            bookmaker_name = bookmaker.get("name", "Unknown")
            
            # Get over/under 2.5 odds
            odds_lookup = {}
            for odd in bookmaker_data.get("bookmaker", {}).get("odds", []):
                if odd.get("value") == "Over 2.5":
                    odds_lookup["over_25"] = odd.get("odds")
                elif odd.get("value") == "Under 2.5":
                    odds_lookup["under_25"] = odd.get("odds")
            
            if not odds_lookup:
                return None
            
            return {
                "fixture_id": fixture_id,
                "bookmaker": bookmaker_name,
                "over_25": odds_lookup.get("over_25"),
                "under_25": odds_lookup.get("under_25"),
                "timestamp": bookmaker_data.get("update")
            }
        except Exception as e:
            logger.warning(f"Failed to get odds for fixture {fixture_id}: {e}")
            return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
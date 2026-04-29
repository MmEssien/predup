"""
Fixture Normalization Layer
Standardizes API responses across all sports into unified schema
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class NormalizedFixture:
    """Normalized fixture output"""
    sport: str
    fixture_id: str
    home_team: str
    away_team: str
    start_time: str
    league: str
    venue: Optional[str] = None
    status: str = "scheduled"
    
    def to_dict(self) -> Dict:
        return {
            "sport": self.sport,
            "fixture_id": self.fixture_id,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "start_time": self.start_time,
            "league": self.league,
            "venue": self.venue,
            "status": self.status,
        }


class FixtureNormalizer:
    """Normalize fixtures from different API responses"""
    
    @staticmethod
    def football(raw: Dict) -> NormalizedFixture:
        """Normalize Football API response"""
        # Handle api-football response format
        teams = raw.get("teams", {})
        league = raw.get("league", {})
        
        home = teams.get("home", {})
        away = teams.get("away", {})
        
        if not home and "home" in raw:
            home = raw.get("home", {})
        if not away and "away" in raw:
            away = raw.get("away", {})
        
        return NormalizedFixture(
            sport="football",
            fixture_id=str(raw.get("id", "")),
            home_team=home.get("name", ""),
            away_team=away.get("name", ""),
            start_time=raw.get("date", ""),
            league=league.get("name", "Unknown"),
            venue=raw.get("venue", {}).get("name") if isinstance(raw.get("venue"), dict) else raw.get("venue"),
            status=raw.get("status", {}).get("short", "NS") if isinstance(raw.get("status"), dict) else raw.get("status", "NS"),
        )
    
    @staticmethod
    def mlb(raw: Dict) -> NormalizedFixture:
        """Normalize MLB API response"""
        # MLBAdapter returns: home_team, away_team, game_datetime, venue, status
        return NormalizedFixture(
            sport="mlb",
            fixture_id=str(raw.get("game_id", raw.get("id", ""))),
            home_team=raw.get("home_team", ""),
            away_team=raw.get("away_team", ""),
            start_time=raw.get("game_datetime", raw.get("start_time", "")),
            league="MLB",
            venue=raw.get("venue", ""),
            status=raw.get("status", "scheduled"),
        )
    
    @staticmethod
    def nba(raw: Dict) -> NormalizedFixture:
        """Normalize NBA API response"""
        teams = raw.get("teams", {})
        
        home = teams.get("home", {}) if isinstance(teams, dict) else {}
        away = teams.get("away", {}) if isinstance(teams, dict) else {}
        
        return NormalizedFixture(
            sport="nba",
            fixture_id=str(raw.get("id", "")),
            home_team=home.get("name", ""),
            away_team=away.get("name", ""),
            start_time=raw.get("date", ""),
            league="NBA",
            venue=None,
            status=raw.get("status", {}).get("short", "NS") if isinstance(raw.get("status"), dict) else "NS",
        )
    
    @staticmethod
    def normalize(raw: Dict, sport: str) -> NormalizedFixture:
        """Route to correct normalizer"""
        normalizers = {
            "football": FixtureNormalizer.football,
            "mlb": FixtureNormalizer.mlb,
            "nba": FixtureNormalizer.nba,
        }
        
        normalizer = normalizers.get(sport.lower())
        if normalizer:
            return normalizer(raw)
        
        raise ValueError(f"Unknown sport: {sport}")


def normalize_fixtures(raw_fixtures: List[Dict], sport: str) -> List[NormalizedFixture]:
    """Normalize list of fixtures"""
    results = []
    
    for raw in raw_fixtures:
        try:
            normalized = FixtureNormalizer.normalize(raw, sport)
            # Skip if missing critical fields
            if not normalized.home_team or not normalized.away_team:
                continue
            results.append(normalized)
        except Exception:
            continue
    
    return results
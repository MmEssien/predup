"""Regime Detector - Match Context Classification"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class RegimeType(Enum):
    """Match regime types"""
    REGULAR = "regular"
    END_OF_SEASON = "end_of_season"
    DERBY = "derby"
    CONGESTION = "congestion"
    EUROPEAN = "european"
    INTERNATIONAL_BREAK = "international_break"
    TITLE_RACE = "title_race"
    RELEGATION_BATTLE = "relegation_battle"
    MUST_WIN = "must_win"


class StakesLevel(Enum):
    """Stakes level for match"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class RegimeResult:
    """Result of regime detection"""
    regime_type: RegimeType
    stakes_level: StakesLevel
    is_derby: bool
    factors: Dict[str, Any]
    recommendations: Dict[str, Any]
    unpredictability_score: float  # Higher = less predictable


class RegimeDetector:
    """Detect match regimes for context-aware predictions"""
    
    # Derby matchups (team pairs)
    DERBY_PAIRS = [
        # Premier League
        ("man_utd", "man_city"),
        ("liverpool", "everton"),
        ("arsenal", "tottenham"),
        ("chelsea", "arsenal"),
        ("chelsea", "tottenham"),
        ("leicester", "nottingham"),
        ("newcastle", "sunderland"),
        ("aston_villa", "birmingham"),
        # Bundesliga
        ("bayern", "dortmund"),
        ("bayern", "münchen1860"),
        ("dortmund", "schalke"),
        ("freiburg", "stuttgart"),
        ("eintracht", "mainz"),
        ("leverkusen", "köln"),
        ("hertha", "union_berlin"),
        # More...
    ]
    
    def __init__(
        self,
        end_of_season_months: List[int] = None,
        min_games_for_congestion: int = 3,
        days_threshold_for_congestion: int = 3
    ):
        self.end_of_season_months = end_of_season_months or [4, 5, 11, 12]
        self.min_games_for_congestion = min_games_for_congestion
        self.days_threshold_for_congestion = days_threshold_for_congestion
        
        # League-specific adjustments
        self.league_contexts = {
            "BL1": {
                "derby_boost_home": 0.02,
                "congestion_impact": -0.05,
                "end_of_season_unpredictability": 0.08,
            },
            "PL": {
                "derby_boost_home": 0.03,
                "congestion_impact": -0.04,
                "end_of_season_unpredictability": 0.10,
            },
            "PD": {
                "derby_boost_home": 0.02,
                "congestion_impact": -0.03,
                "end_of_season_unpredictability": 0.05,
            }
        }
    
    def detect_regime(
        self,
        fixture_data: Dict[str, Any],
        table_data: Optional[Dict[str, Any]] = None,
        recent_fixtures: Optional[List[Dict]] = None
    ) -> RegimeResult:
        """Detect regime for a fixture"""
        
        factors = {}
        
        # 1. Check for derby
        is_derby, derby_type = self._detect_derby(
            fixture_data.get("home_team"),
            fixture_data.get("away_team"),
            fixture_data.get("competition_code")
        )
        factors["is_derby"] = is_derby
        factors["derby_type"] = derby_type
        
        # 2. Check for end of season
        is_end_of_season = self._is_end_of_season(fixture_data.get("utc_date"))
        factors["is_end_of_season"] = is_end_of_season
        
        # 3. Check for fixture congestion
        congestion_info = self._check_congestion(
            fixture_data.get("home_team"),
            fixture_data.get("away_team"),
            fixture_data.get("utc_date"),
            recent_fixtures
        )
        factors["congestion"] = congestion_info
        
        # 4. Check European competition effect
        european_effect = self._check_european_effect(
            fixture_data.get("home_team"),
            recent_fixtures
        )
        factors["european_nights"] = european_effect
        
        # 5. Determine stakes level
        stakes_level, title_relegation_info = self._determine_stakes(
            fixture_data, table_data
        )
        factors["stakes"] = stakes_level
        factors["title_relegation"] = title_relegation_info
        
        # 6. Determine primary regime type
        regime_type = self._determine_regime_type(
            is_derby=is_derby,
            is_end_of_season=is_end_of_season,
            congestion_info=congestion_info,
            stakes_level=stakes_level,
            european_effect=european_effect
        )
        
        # 7. Calculate unpredictability score
        unpredictability = self._calculate_unpredictability(
            regime_type, is_derby, is_end_of_season, congestion_info
        )
        
        # 8. Generate recommendations
        recommendations = self._get_recommendations(
            regime_type, stakes_level, unpredictability
        )
        
        return RegimeResult(
            regime_type=regime_type,
            stakes_level=stakes_level,
            is_derby=is_derby,
            factors=factors,
            recommendations=recommendations,
            unpredictability_score=unpredictability
        )
    
    def _detect_derby(
        self,
        home_team: str,
        away_team: str,
        competition: str
    ) -> Tuple[bool, str]:
        """Detect if match is a derby"""
        
        if not home_team or not away_team:
            return False, ""
        
        team1 = home_team.lower().replace(" ", "_")
        team2 = away_team.lower().replace(" ", "_")
        
        # Check against known derby pairs
        for pair in self.DERBY_PAIRS:
            if (team1 in pair and team2 in pair) or \
               (team2 in pair and team1 in pair):
                return True, f"{pair[0]}_vs_{pair[1]}"
        
        # Check city-based derbies
        home_city = self._extract_city(team1)
        away_city = self._extract_city(team2)
        
        if home_city and away_city and home_city == away_city:
            return True, f"city_derby_{home_city}"
        
        return False, ""
    
    def _extract_city(self, team_name: str) -> Optional[str]:
        """Extract city from team name"""
        # Simple extraction - can be enhanced
        city_patterns = {
            "manchester": "manchester",
            "london": "london",
            "milan": "milan",
            "madrid": "madrid",
            "berlin": "berlin",
            "munich": "munich",
            "dortmund": "dortmund",
        }
        
        for pattern, city in city_patterns.items():
            if pattern in team_name:
                return city
        
        return None
    
    def _is_end_of_season(self, utc_date) -> bool:
        """Check if match is at end of season"""
        
        if isinstance(utc_date, str):
            try:
                utc_date = datetime.fromisoformat(utc_date.replace("Z", "+00:00"))
            except:
                return False
        
        if isinstance(utc_date, datetime):
            return utc_date.month in self.end_of_season_months
        
        return False
    
    def _check_congestion(
        self,
        home_team: str,
        away_team: str,
        match_date,
        recent_fixtures: Optional[List[Dict]]
    ) -> Dict[str, Any]:
        """Check for fixture congestion"""
        
        if not recent_fixtures:
            return {"has_congestion": False, "affected_teams": []}
        
        if isinstance(match_date, str):
            try:
                match_date = datetime.fromisoformat(match_date.replace("Z", "+00:00"))
            except:
                match_date = None
        
        if not match_date:
            return {"has_congestion": False, "affected_teams": []}
        
        home_congestion = 0
        away_congestion = 0
        
        for fixture in recent_fixtures:
            fixture_date = fixture.get("utc_date")
            if isinstance(fixture_date, str):
                try:
                    fixture_date = datetime.fromisoformat(fixture_date.replace("Z", "+00:00"))
                except:
                    continue
            
            if fixture_date:
                days_diff = (match_date - fixture_date).days
                
                if days_diff <= 72 and days_diff >= 0:  # Last ~10 weeks
                    if fixture.get("home_team") == home_team or fixture.get("away_team") == home_team:
                        home_congestion += 1
                    if fixture.get("home_team") == away_team or fixture.get("away_team") == away_team:
                        away_congestion += 1
        
        affected = []
        if home_congestion >= self.min_games_for_congestion:
            affected.append("home")
        if away_congestion >= self.min_games_for_congestion:
            affected.append("away")
        
        return {
            "has_congestion": len(affected) > 0,
            "affected_teams": affected,
            "home_games_last_10_weeks": home_congestion,
            "away_games_last_10_weeks": away_congestion
        }
    
    def _check_european_effect(
        self,
        team: str,
        recent_fixtures: Optional[List[Dict]]
    ) -> Dict[str, Any]:
        """Check for European competition effect"""
        
        if not recent_fixtures:
            return {"has_european": False}
        
        # Look for CL/EL fixtures in last 2 weeks
        european_competitions = ["CL", "EL", "UCL", "UEL"]
        
        recent_european = []
        for fixture in recent_fixtures:
            comp = fixture.get("competition_code")
            if comp in european_competitions:
                recent_european.append(fixture)
        
        if recent_european:
            return {
                "has_european": True,
                "european_games": len(recent_european),
                "comp": recent_european[0].get("competition_code")
            }
        
        return {"has_european": False}
    
    def _determine_stakes(
        self,
        fixture_data: Dict,
        table_data: Optional[Dict]
    ) -> Tuple[StakesLevel, Dict]:
        """Determine stakes level for match"""
        
        if not table_data:
            return StakesLevel.MEDIUM, {}
        
        # Check for title race / relegation
        home_pos = table_data.get("home_position")
        away_pos = table_data.get("away_position")
        
        title_relegation_info = {}
        
        # Title race (top 4)
        if home_pos and home_pos <= 4:
            title_relegation_info["home_title_race"] = True
        if away_pos and away_pos <= 4:
            title_relegation_info["away_title_race"] = True
        
        # Relegation battle (bottom 3)
        if home_pos and home_pos >= 18:
            title_relegation_info["home_relegation_battle"] = True
        if away_pos and away_pos >= 18:
            title_relegation_info["away_relegation_battle"] = True
        
        # Determine stakes
        if title_relegation_info.get("home_title_race") or title_relegation_info.get("away_title_race"):
            stakes = StakesLevel.HIGH
        elif title_relegation_info.get("home_relegation_battle") or title_relegation_info.get("away_relegation_battle"):
            stakes = StakesLevel.HIGH
        else:
            stakes = StakesLevel.MEDIUM
        
        return stakes, title_relegation_info
    
    def _determine_regime_type(
        self,
        is_derby: bool,
        is_end_of_season: bool,
        congestion_info: Dict,
        stakes_level: StakesLevel,
        european_effect: Dict
    ) -> RegimeType:
        """Determine primary regime type"""
        
        if is_derby:
            return RegimeType.DERBY
        
        if is_end_of_season:
            return RegimeType.END_OF_SEASON
        
        if congestion_info.get("has_congestion"):
            return RegimeType.CONGESTION
        
        if european_effect.get("has_european"):
            return RegimeType.EUROPEAN
        
        if stakes_level == StakesLevel.HIGH:
            if congestion_info.get("title_relegation", {}).get("home_relegation_battle") or \
               congestion_info.get("title_relegation", {}).get("away_relegation_battle"):
                return RegimeType.RELEGATION_BATTLE
            return RegimeType.TITLE_RACE
        
        return RegimeType.REGULAR
    
    def _calculate_unpredictability(
        self,
        regime_type: RegimeType,
        is_derby: bool,
        is_end_of_season: bool,
        congestion_info: Dict
    ) -> float:
        """Calculate unpredictability score"""
        
        base_unpredictability = {
            RegimeType.REGULAR: 0.3,
            RegimeType.TITLE_RACE: 0.4,
            RegimeType.RELEGATION_BATTLE: 0.45,
            RegimeType.END_OF_SEASON: 0.5,
            RegimeType.DERBY: 0.55,
            RegimeType.CONGESTION: 0.45,
            RegimeType.EUROPEAN: 0.35,
            RegimeType.INTERNATIONAL_BREAK: 0.4,
            RegimeType.MUST_WIN: 0.4,
        }.get(regime_type, 0.3)
        
        # Adjust for congestion
        if congestion_info.get("has_congestion"):
            base_unpredictability += 0.1
        
        # Adjust for derby
        if is_derby:
            base_unpredictability += 0.1
        
        return min(base_unpredictability, 0.8)
    
    def _get_recommendations(
        self,
        regime_type: RegimeType,
        stakes_level: StakesLevel,
        unpredictability: float
    ) -> Dict[str, Any]:
        """Get recommendations based on regime"""
        
        recommendations = {}
        
        # Threshold adjustments
        if regime_type == RegimeType.DERBY:
            recommendations["threshold_boost"] = 0.05
            recommendations["min_odds"] = 1.8
            recommendations["description"] = "Derby matches are less predictable - raise threshold"
        
        elif regime_type == RegimeType.END_OF_SEASON:
            recommendations["threshold_boost"] = 0.03
            recommendations["description"] = "End of season can be unpredictable - slight caution"
        
        elif regime_type == RegimeType.CONGESTION:
            recommendations["threshold_boost"] = 0.02
            recommendations["description"] = "Fatigue from congestion - be cautious"
        
        elif regime_type == RegimeType.TITLE_RACE:
            recommendations["threshold_boost"] = -0.02  # Lower threshold - more opportunities
            recommendations["description"] = "Title race teams more motivated"
        
        elif regime_type == RegimeType.RELEGATION_BATTLE:
            recommendations["threshold_boost"] = 0.02
            recommendations["description"] = "Relegation battles can be unpredictable"
        
        else:
            recommendations["threshold_boost"] = 0
            recommendations["description"] = "Regular match - use standard settings"
        
        # Variance adjustment
        recommendations["variance_penalty"] = unpredictability * 0.1
        
        return recommendations
    
    def apply_regime_adjustment(
        self,
        base_probability: float,
        regime_result: RegimeResult,
        confidence: float = 1.0
    ) -> float:
        """Apply regime adjustments to probability"""
        
        if regime_result.regime_type == RegimeType.REGULAR:
            return base_probability
        
        adjustments = regime_result.recommendations
        
        # Derbys - slightly reduce home probability (less predictable)
        if regime_result.is_derby:
            base_probability = base_probability * 0.95
        
        # High stakes - increase home/motivation effect
        if regime_result.stakes_level == StakesLevel.HIGH:
            # If not already in the direction of the team fighting for something
            if base_probability != 0.5:
                adjustment = 0.02 * confidence
                if base_probability > 0.5:
                    base_probability += adjustment
                else:
                    base_probability -= adjustment
        
        # End of season - regress toward 0.5
        if regime_result.regime_type == RegimeType.END_OF_SEASON:
            base_probability = 0.5 + (base_probability - 0.5) * 0.9
        
        # Congestion - regress slightly toward 0.5
        if regime_result.regime_type == RegimeType.CONGESTION:
            base_probability = 0.5 + (base_probability - 0.5) * 0.95
        
        return max(0.01, min(0.99, base_probability))
    
    def get_regime_model_params(self, regime: RegimeType) -> Dict[str, Any]:
        """Get model parameters for specific regime"""
        
        regime_params = {
            RegimeType.REGULAR: {
                "confidence_multiplier": 1.0,
                "variance_threshold": 0.08
            },
            RegimeType.DERBY: {
                "confidence_multiplier": 0.85,
                "variance_threshold": 0.10,
                "min_odds": 1.9
            },
            RegimeType.END_OF_SEASON: {
                "confidence_multiplier": 0.90,
                "variance_threshold": 0.10,
                "additional_caution": True
            },
            RegimeType.CONGESTION: {
                "confidence_multiplier": 0.92,
                "variance_threshold": 0.09
            },
            RegimeType.RELEGATION_BATTLE: {
                "confidence_multiplier": 0.88,
                "variance_threshold": 0.10
            },
            RegimeType.TITLE_RACE: {
                "confidence_multiplier": 1.05,
                "variance_threshold": 0.07
            }
        }
        
        return regime_params.get(regime, regime_params[RegimeType.REGULAR])
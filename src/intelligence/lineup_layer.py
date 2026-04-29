"""Lineup Layer - Pre-match adjustments for injuries, suspensions, lineups"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class LineupImpact:
    """Impact of a player on match probability"""
    player_name: str
    position: str
    impact_type: str  # injury, suspension, missing
    severity: float  # 0.0 - 1.0 (how much it affects probability)
    team: str  # home or away
    is_key_player: bool


@dataclass
class LineupAdjustment:
    """Total lineup adjustment result"""
    home_adjustment: float
    away_adjustment: float
    net_adjustment: float
    key_absences: List[LineupImpact]
    confidence_reduction: float  # How much less confident we should be


class LineupLayer:
    """
    Pre-match layer for adjusting probabilities based on:
    - Player injuries
    - suspensions
    - Missing players (international duty, etc.)
    - Starting lineup confirmation
    """
    
    # Position weights for importance
    POSITION_WEIGHTS = {
        "GK": 0.08,      # Goalkeeper - high impact on clean sheets
        "DEF": 0.12,     # Defender
        "MID": 0.15,     # Midfielder - key playmaker
        "ATT": 0.20,     # Attacker - goal scorer
        "FWD": 0.22,     # Forward - highest impact
    }
    
    # Key player multiplier
    KEY_PLAYER_MULTIPLIER = 1.5
    
    def __init__(self, default_severity: float = 0.1):
        self.default_severity = default_severity
        self._impact_cache: Dict[int, LineupAdjustment] = {}
    
    def calculate_adjustment(
        self,
        lineup_data: Dict[str, Any],
        prediction_direction: str = "home_win"
    ) -> float:
        """
        Calculate probability adjustment based on lineup data.
        
        Args:
            lineup_data: Dict containing:
                - home_missing: List of missing player dicts
                - away_missing: List of missing player dicts  
                - home_confirmed: List of confirmed starters
                - away_confirmed: List of confirmed starters
                - fixture_id: Optional fixture ID for caching
            prediction_direction: "home_win", "draw", or "away_win"
            
        Returns:
            Probability adjustment (-0.1 to +0.1)
        """
        home_impact = 0.0
        away_impact = 0.0
        
        # Process home team absences
        for absence in lineup_data.get("home_missing", []):
            impact = self._calculate_player_impact(absence, "home")
            home_impact += impact
        
        # Process away team absences
        for absence in lineup_data.get("away_missing", []):
            impact = self._calculate_player_impact(absence, "away")
            away_impact += impact
        
        # Net adjustment: positive means home win more likely
        net = home_impact - away_impact
        
        # Adjust based on prediction direction
        if prediction_direction == "away_win":
            net = -net
        elif prediction_direction == "draw":
            net = abs(net) * 0.3  # Reduce impact for draws
        else:
            net = net  # home_win
        
        # Clamp to reasonable range
        return np.clip(net, -0.1, 0.1)
    
    def _calculate_player_impact(
        self,
        absence: Dict[str, Any],
        team: str
    ) -> LineupImpact:
        """Calculate impact of a single player absence"""
        
        player_name = absence.get("name", "Unknown")
        position = absence.get("position", "MID")
        severity = absence.get("severity", self.default_severity)
        is_key = absence.get("is_key_player", False)
        
        # Base impact from position
        position_weight = self.POSITION_WEIGHTS.get(position, 0.15)
        
        # Calculate total impact
        impact = severity * position_weight
        
        # Apply key player multiplier
        if is_key:
            impact *= self.KEY_PLAYER_MULTIPLIER
        
        return LineupImpact(
            player_name=player_name,
            position=position,
            impact_type=absence.get("type", "unknown"),
            severity=impact,
            team=team,
            is_key_player=is_key
        )
    
    def get_lineup_adjustment(
        self,
        home_missing: List[Dict],
        away_missing: List[Dict],
        fixture_id: Optional[int] = None
    ) -> LineupAdjustment:
        """Get complete lineup adjustment"""
        
        # Check cache
        if fixture_id and fixture_id in self._impact_cache:
            return self._impact_cache[fixture_id]
        
        home_adjustment = 0.0
        away_adjustment = 0.0
        key_absences = []
        
        for absence in home_missing:
            impact = self._calculate_player_impact(absence, "home")
            home_adjustment += impact.severity
            if impact.is_key_player:
                key_absences.append(impact)
        
        for absence in away_missing:
            impact = self._calculate_player_impact(absence, "away")
            away_adjustment += impact.severity
            if impact.is_key_player:
                key_absences.append(impact)
        
        net = home_adjustment - away_adjustment
        
        # Confidence reduction based on key absences
        confidence_reduction = min(len(key_absences) * 0.05, 0.25)
        
        adjustment = LineupAdjustment(
            home_adjustment=home_adjustment,
            away_adjustment=away_adjustment,
            net_adjustment=net,
            key_absences=key_absences,
            confidence_reduction=confidence_reduction
        )
        
        # Cache result
        if fixture_id:
            self._impact_cache[fixture_id] = adjustment
        
        return adjustment
    
    def adjust_probability(
        self,
        base_probability: float,
        lineup_adjustment: LineupAdjustment,
        direction: str = "home_win"
    ) -> float:
        """
        Adjust base probability using lineup information.
        
        Args:
            base_probability: Base model probability
            lineup_adjustment: Pre-calculated lineup adjustment
            direction: "home_win", "draw", or "away_win"
            
        Returns:
            Adjusted probability
        """
        if direction == "home_win":
            # Home team weakened reduces home win probability
            adjustment = -lineup_adjustment.home_adjustment + lineup_adjustment.away_adjustment
        elif direction == "away_win":
            # Away team weakened reduces away win probability
            adjustment = lineup_adjustment.home_adjustment - lineup_adjustment.away_adjustment
        else:
            # Draw: reduces extreme probabilities
            adjustment = -abs(lineup_adjustment.net_adjustment) * 0.5
        
        adjusted = base_probability + adjustment
        
        return np.clip(adjusted, 0.01, 0.99)
    
    def should_reduce_confidence(
        self,
        lineup_adjustment: LineupAdjustment,
        threshold: float = 0.1
    ) -> bool:
        """Check if lineup uncertainty should reduce prediction confidence"""
        return (
            len(lineup_adjustment.key_absences) >= 2 or
            lineup_adjustment.confidence_reduction >= threshold or
            abs(lineup_adjustment.net_adjustment) >= 0.15
        )
    
    def get_impact_summary(
        self,
        lineup_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Get human-readable summary of lineup impact"""
        
        home_missing = lineup_data.get("home_missing", [])
        away_missing = lineup_data.get("away_missing", [])
        
        home_impact = self.get_lineup_adjustment(home_missing, [])
        away_impact = self.get_lineup_adjustment([], away_missing)
        
        return {
            "home_absences": len(home_missing),
            "away_absences": len(away_missing),
            "home_key_absences": [p.player_name for p in home_impact.key_absences],
            "away_key_absences": [p.player_name for p in away_impact.key_absences],
            "net_impact": home_impact.net_adjustment - away_impact.net_adjustment,
            "impact_direction": "favors_home" if home_impact.net_adjustment > away_impact.net_adjustment else "favors_away",
            "confidence_affected": self.should_reduce_confidence(
                LineupAdjustment(
                    home_adjustment=home_impact.home_adjustment,
                    away_adjustment=away_impact.away_adjustment,
                    net_adjustment=home_impact.net_adjustment - away_impact.net_adjustment,
                    key_absences=home_impact.key_absences + away_impact.key_absences,
                    confidence_reduction=home_impact.confidence_reduction + away_impact.confidence_reduction
                )
            )
        }


def fetch_injuries_for_team(
    api_client,
    team_id: int,
    league_code: str,
    match_date: datetime
) -> List[Dict]:
    """Fetch current injuries for a team"""
    
    try:
        response = api_client.get(f"/teams/{team_id}/injuries")
        injuries = []
        
        for injury in response.get("response", []):
            player = injury.get("player", {})
            
            injuries.append({
                "name": player.get("name"),
                "position": player.get("position"),
                "type": "injury",
                "reason": injury.get("reason"),
                "return_date": injury.get("returnDate"),
                "is_key_player": player.get("injured", False)
            })
        
        return injuries
    
    except Exception as e:
        logger.warning(f"Could not fetch injuries for team {team_id}: {e}")
        return []


def fetch_suspensions_for_team(
    api_client,
    team_id: int,
    match_date: datetime
) -> List[Dict]:
    """Fetch suspended players for a team"""
    
    try:
        response = api_client.get(f"/teams/{team_id}/suspensions")
        suspensions = []
        
        for susp in response.get("response", []):
            player = susp.get("player", {})
            
            suspensions.append({
                "name": player.get("name"),
                "position": player.get("position"),
                "type": "suspension",
                "reason": susp.get("reason"),
                "matches_remaining": susp.get("matchesRemaining"),
                "is_key_player": player.get("suspended", False)
            })
        
        return suspensions
    
    except Exception as e:
        logger.warning(f"Could not fetch suspensions for team {team_id}: {e}")
        return []


def fetch_lineup_confirmation(
    api_client,
    fixture_id: int
) -> Dict[str, Any]:
    """Fetch confirmed lineup before match"""
    
    try:
        response = api_client.get(f"/fixtures/{fixture_id}/lineups")
        
        lineups = {"home": [], "away": []}
        
        for team_data in response.get("response", []):
            team = team_data.get("team", {}).get("name", "Unknown")
            formation = team_data.get("formation", {})
            
            starters = formation.get("startXI", [])
            missing = formation.get("missingPlayers", [])
            
            if "home" in team.lower() or "home" not in lineups:
                lineups["home"] = {
                    "formation": formation.get("formation"),
                    "starters": [p.get("player", {}).get("name") for p in starters],
                    "missing": missing
                }
            else:
                lineups["away"] = {
                    "formation": formation.get("formation"),
                    "starters": [p.get("player", {}).get("name") for p in starters],
                    "missing": missing
                }
        
        return lineups
    
    except Exception as e:
        logger.warning(f"Could not fetch lineup for fixture {fixture_id}: {e}")
        return {"home": {}, "away": {}}


def compose_lineup_data(
    fixture_id: int,
    home_team_id: int,
    away_team_id: int,
    api_client,
    match_date: datetime,
    stored_injuries: Optional[List[Dict]] = None
) -> Dict[str, Any]:
    """
    Compose complete lineup data from multiple sources.
    
    Priority:
    1. Confirmed lineups (if match day)
    2. Stored injuries from database
    3. API fetched injuries/suspensions
    """
    
    lineup_data = {
        "fixture_id": fixture_id,
        "home_missing": [],
        "away_missing": [],
        "home_confirmed": [],
        "away_confirmed": [],
        "data_freshness": "unknown"
    }
    
    # Try confirmed lineups first
    confirmed = fetch_lineup_confirmation(api_client, fixture_id)
    if confirmed.get("home") and confirmed.get("away"):
        lineup_data["home_confirmed"] = confirmed["home"].get("starters", [])
        lineup_data["away_confirmed"] = confirmed["away"].get("starters", [])
        lineup_data["data_freshness"] = "confirmed"
    else:
        # Use stored or API injuries
        injuries = stored_injuries or []
        
        for injury in injuries:
            if injury.get("team_id") == home_team_id:
                lineup_data["home_missing"].append(injury)
            elif injury.get("team_id") == away_team_id:
                lineup_data["away_missing"].append(injury)
        
        # Fetch from API if no stored data
        if not injuries:
            home_injuries = fetch_injuries_for_team(api_client, home_team_id, None, match_date)
            away_injuries = fetch_injuries_for_team(api_client, away_team_id, None, match_date)
            
            # Convert to standard format
            for inj in home_injuries:
                lineup_data["home_missing"].append({
                    "name": inj["name"],
                    "position": inj["position"],
                    "type": "injury",
                    "is_key_player": inj.get("is_key_player", False)
                })
            
            for inj in away_injuries:
                lineup_data["away_missing"].append({
                    "name": inj["name"],
                    "position": inj["position"],
                    "type": "injury",
                    "is_key_player": inj.get("is_key_player", False)
                })
            
            # Add suspensions
            home_susp = fetch_suspensions_for_team(api_client, home_team_id, match_date)
            away_susp = fetch_suspensions_for_team(api_client, away_team_id, match_date)
            
            for susp in home_susp:
                lineup_data["home_missing"].append({
                    "name": susp["name"],
                    "position": susp["position"],
                    "type": "suspension",
                    "is_key_player": True  # Suspensions are usually key players
                })
            
            for susp in away_susp:
                lineup_data["away_missing"].append({
                    "name": susp["name"],
                    "position": susp["position"],
                    "type": "suspension",
                    "is_key_player": True
                })
            
            lineup_data["data_freshness"] = "fetched"
    
    return lineup_data
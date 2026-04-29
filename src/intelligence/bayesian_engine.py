"""Bayesian Updating Engine for Dynamic Probability Adjustment"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import logging
import math

logger = logging.getLogger(__name__)


class EvidenceType(Enum):
    """Types of evidence for Bayesian updating"""
    LINEUP_CONFIRMED = "lineup_confirmed"
    INJURY_KEY_PLAYER = "injury_key_player"
    INJURY_ROLE_PLAYER = "injury_role_player"
    WEATHER_ADVERSE = "weather_adverse"
    WEATHER_FAVORABLE = "weather_favorable"
    ODDS_MOVEMENT = "odds_movement"
    PUBLIC_BETTING = "public_betting"
    SHARP_MONEY = "sharp_money"
    TEAM_NEWS = "team_news"
    REST_DAYS = "rest_days"
    HOME_ADVANTAGE = "home_advantage"
    DERBY = "derby"


@dataclass
class Evidence:
    """Evidence for Bayesian update"""
    evidence_type: EvidenceType
    strength: float  # 0-1 confidence in this evidence
    direction: float  # -1 to 1 (negative to positive impact on home win)
    description: str
    timestamp: Optional[datetime] = None


@dataclass
class BayesianResult:
    """Result of Bayesian updating"""
    original_probability: float
    updated_probability: float
    evidence_applied: List[str]
    total_adjustment: float
    confidence: float


class BayesianEngine:
    """Bayesian probability updating engine"""
    
    # Default impact factors for evidence types
    EVIDENCE_IMPACTS = {
        EvidenceType.INJURY_KEY_PLAYER: -0.15,  # Star player out
        EvidenceType.INJURY_ROLE_PLAYER: -0.08,  # Regular starter out
        EvidenceType.WEATHER_ADVERSE: -0.05,     # Bad weather
        EvidenceType.WEATHER_FAVORABLE: 0.03,   # Good weather
        EvidenceType.ODDS_MOVEMENT: 0.05,       # Odds moved significantly
        EvidenceType.SHARP_MONEY: 0.08,          # Sharp money on this side
        EvidenceType.PUBLIC_BETTING: -0.03,      # Public heavily on this side
        EvidenceType.REST_DAYS: 0.04,            # More rest days
        EvidenceType.HOME_ADVANTAGE: 0.05,       # Home team advantage
        EvidenceType.DERBY: 0.0,                 # Derbies are unpredictable
    }
    
    def __init__(
        self,
        max_adjustment: float = 0.25,    # Max total adjustment (25%)
        confidence_decay: float = 0.90,   # Evidence confidence decays over time
        league_adjustments: Optional[Dict[str, Dict]] = None
    ):
        self.max_adjustment = max_adjustment
        self.confidence_decay = confidence_decay
        
        # League-specific adjustments
        self.league_adjustments = league_adjustments or {
            "BL1": {
                "home_advantage": 0.06,  # Higher home advantage in Germany
                "derby_unpredictable": True,
            },
            "PL": {
                "home_advantage": 0.05,
                "derby_unpredictable": True,
            },
            "PD": {
                "home_advantage": 0.05,
                "derby_unpredictable": False,  # Derbies more predictable in Spain
            },
            "SA": {
                "home_advantage": 0.04,
                "derby_unpredictable": True,
            }
        }
    
    def update_probability(
        self,
        base_probability: float,
        evidence: List[Evidence],
        league_code: Optional[str] = None,
        apply_league_factors: bool = True
    ) -> BayesianResult:
        """Update probability with Bayesian evidence"""
        
        if not evidence:
            return BayesianResult(
                original_probability=base_probability,
                updated_probability=base_probability,
                evidence_applied=[],
                total_adjustment=0,
                confidence=1.0
            )
        
        current_prob = base_probability
        applied_evidence = []
        total_adjustment = 0
        
        # Get league-specific factors
        league_factors = self.league_adjustments.get(league_code, {}) if apply_league_factors else {}
        
        for ev in evidence:
            # Get base impact for this evidence type
            base_impact = self.EVIDENCE_IMPACTS.get(ev.evidence_type, 0)
            
            # Adjust for league
            if ev.evidence_type == EvidenceType.HOME_ADVANTAGE and apply_league_factors:
                base_impact = league_factors.get("home_advantage", 0.05)
            
            # Apply evidence direction
            impact = base_impact * ev.direction * ev.strength
            
            # Apply uncertainty (we're never 100% sure)
            confidence_factor = ev.strength
            
            # Calculate update using log-odds (more accurate for probabilities)
            current_odds = current_prob / (1 - current_prob) if current_prob < 0.99 else 100
            log_odds = math.log(current_odds)
            
            # Bayesian update in log-odds space
            bayesian_update = math.log((1 + impact) / (1 - impact)) * confidence_factor if abs(impact) < 1 else 0
            new_log_odds = log_odds + bayesian_update
            
            # Convert back to probability
            new_prob = 1 / (1 + math.exp(-new_log_odds))
            
            # Apply max adjustment constraint
            adjustment = new_prob - current_prob
            if abs(adjustment) > self.max_adjustment:
                new_prob = current_prob + (self.max_adjustment if adjustment > 0 else -self.max_adjustment)
                adjustment = new_prob - current_prob
            
            current_prob = new_prob
            total_adjustment += adjustment
            applied_evidence.append(ev.description)
        
        # Calculate overall confidence based on evidence strength
        avg_evidence_strength = sum(e.strength for e in evidence) / len(evidence)
        confidence = min(avg_evidence_strength * 1.2, 1.0)
        
        return BayesianResult(
            original_probability=base_probability,
            updated_probability=current_prob,
            evidence_applied=applied_evidence,
            total_adjustment=total_adjustment,
            confidence=confidence
        )
    
    def update_from_events(
        self,
        base_probability: float,
        events: List[Dict[str, Any]],
        league_code: Optional[str] = None
    ) -> BayesianResult:
        """Update probability from event data"""
        
        evidence_list = []
        
        for event in events:
            ev_type = event.get("type", "")
            strength = event.get("strength", 0.5)
            direction = event.get("direction", 0)
            
            # Map event type to EvidenceType
            try:
                evidence_type = EvidenceType(ev_type)
            except ValueError:
                logger.warning(f"Unknown evidence type: {ev_type}")
                continue
            
            evidence = Evidence(
                evidence_type=evidence_type,
                strength=strength,
                direction=direction,
                description=event.get("description", ""),
                timestamp=event.get("timestamp")
            )
            evidence_list.append(evidence)
        
        return self.update_probability(base_probability, evidence_list, league_code)
    
    def get_pre_match_evidence(
        self,
        fixture_data: Dict[str, Any],
        odds_movement: Optional[float] = None,
        public_betting_pct: Optional[float] = None
    ) -> List[Evidence]:
        """Generate pre-match evidence from fixture data"""
        
        evidence = []
        
        # Home advantage
        evidence.append(Evidence(
            evidence_type=EvidenceType.HOME_ADVANTAGE,
            strength=0.8,
            direction=1 if fixture_data.get("is_home", True) else -1,
            description="Home team advantage"
        ))
        
        # Rest days
        rest_days = fixture_data.get("rest_days", 7)
        if rest_days >= 5:
            evidence.append(Evidence(
                evidence_type=EvidenceType.REST_DAYS,
                strength=0.6,
                direction=1,
                description=f"Good rest: {rest_days} days"
            ))
        elif rest_days < 3:
            evidence.append(Evidence(
                evidence_type=EvidenceType.REST_DAYS,
                strength=0.7,
                direction=-1,
                description=f"Short rest: {rest_days} days"
            ))
        
        # Key player injuries
        key_out = fixture_data.get("key_players_out", [])
        if key_out:
            evidence.append(Evidence(
                evidence_type=EvidenceType.INJURY_KEY_PLAYER,
                strength=min(len(key_out) * 0.3, 0.9),
                direction=-1,
                description=f"Key players out: {', '.join(key_out)}"
            ))
        
        # Odds movement
        if odds_movement and abs(odds_movement) > 0.05:
            direction = -1 if odds_movement > 0 else 1  # Odds down = more likely
            evidence.append(Evidence(
                evidence_type=EvidenceType.ODDS_MOVEMENT,
                strength=min(abs(odds_movement) * 2, 0.8),
                direction=direction,
                description=f"Odds moved {odds_movement:.1%}"
            ))
        
        # Public betting
        if public_betting_pct:
            if public_betting_pct > 0.75:
                evidence.append(Evidence(
                    evidence_type=EvidenceType.PUBLIC_BETTING,
                    strength=0.5,
                    direction=-1,  # Contrarian: public usually wrong
                    description=f"Heavy public betting: {public_betting_pct:.0%}"
                ))
        
        # Derby
        if fixture_data.get("is_derby"):
            evidence.append(Evidence(
                evidence_type=EvidenceType.DERBY,
                strength=0.5,
                direction=0,  # Derbies are unpredictable
                description="Derby match"
            ))
        
        # Weather
        if fixture_data.get("weather"):
            weather = fixture_data["weather"]
            if weather.get("is_adverse"):
                evidence.append(Evidence(
                    evidence_type=EvidenceType.WEATHER_ADVERSE,
                    strength=0.4,
                    direction=-1,
                    description=f"Adverse weather: {weather.get('description', 'bad')}"
                ))
        
        return evidence
    
    def get_in_play_evidence(
        self,
        in_play_data: Dict[str, Any],
        elapsed_minutes: int
    ) -> List[Evidence]:
        """Generate in-play evidence from live game data"""
        
        evidence = []
        
        # Goals scored
        if in_play_data.get("home_goals", 0) > in_play_data.get("away_goals", 0):
            direction = 1
        elif in_play_data.get("home_goals", 0) < in_play_data.get("away_goals", 0):
            direction = -1
        else:
            direction = 0
        
        if direction != 0:
            evidence.append(Evidence(
                evidence_type=EvidenceType.TEAM_NEWS,
                strength=0.9,
                direction=direction,
                description=f"Home team leading {in_play_data.get('home_goals', 0)}-{in_play_data.get('away_goals', 0)}"
            ))
        
        # Red cards
        home_reds = in_play_data.get("home_red_cards", 0)
        away_reds = in_play_data.get("away_red_cards", 0)
        
        if home_reds > away_reds:
            evidence.append(Evidence(
                evidence_type=EvidenceType.TEAM_NEWS,
                strength=0.8,
                direction=1 if in_play_data.get("home_goals", 0) > in_play_data.get("away_goals", 0) else -1,
                description=f"Home team down to {11-home_reds} men"
            ))
        elif away_reds > home_reds:
            evidence.append(Evidence(
                evidence_type=EvidenceType.TEAM_NEWS,
                strength=0.8,
                direction=1 if in_play_data.get("home_goals", 0) < in_play_data.get("away_goals", 0) else -1,
                description="Away team reduced to 10 men"
            ))
        
        # Time elapsed factor (less time = less impact of current state)
        time_factor = min(elapsed_minutes / 90, 1.0)
        
        return evidence
    
    def calculate_momentum_adjustment(
        self,
        base_probability: float,
        recent_events: List[Dict],
        decay_factor: float = 0.8
    ) -> float:
        """Calculate momentum-based adjustment from recent events"""
        
        if not recent_events:
            return base_probability
        
        momentum = 0
        
        for i, event in enumerate(recent_events):
            # Weight recent events more heavily
            weight = decay_factor ** i
            
            if event.get("type") == "goal":
                scorer = event.get("scorer_team", "unknown")
                if scorer == "home":
                    momentum += weight * 0.05
                else:
                    momentum -= weight * 0.05
            elif event.get("type") == "red_card":
                recipient = event.get("team", "unknown")
                if recipient == "home":
                    momentum -= weight * 0.10
                else:
                    momentum += weight * 0.10
        
        # Apply momentum to probability
        adjusted_prob = base_probability + momentum
        
        # Keep in valid range
        return max(0.01, min(0.99, adjusted_prob))
    
    def adapt_to_market(
        self,
        model_probability: float,
        market_implied: float,
        kelly_evidence_strength: float = 0.3
    ) -> float:
        """Adapt model probability based on market with Kelly evidence"""
        
        # If model and market diverge significantly, weight toward market
        divergence = abs(model_probability - market_implied)
        
        if divergence > 0.15:
            # Significant divergence - weight based on Kelly
            market_weight = kelly_evidence_strength
            
            # Fade heavily bet public (contrarian)
            blended = model_probability * (1 - market_weight) + market_implied * market_weight
            
            logger.info(f"Market adaptation: model={model_probability:.3f}, market={market_implied:.3f}, adapted={blended:.3f}")
            return blended
        
        return model_probability
    
    def get_confidence_bands(
        self,
        probability: float,
        evidence_strength: float
    ) -> Dict[str, Any]:
        """Get confidence bands based on probability and evidence"""
        
        # High evidence = tighter bands
        if evidence_strength > 0.7:
            band_width = 0.05
        elif evidence_strength > 0.5:
            band_width = 0.08
        else:
            band_width = 0.12
        
        return {
            "probability": probability,
            "lower": max(0.01, probability - band_width),
            "upper": min(0.99, probability + band_width),
            "band_width": band_width,
            "confidence": "high" if evidence_strength > 0.6 else "medium" if evidence_strength > 0.4 else "low"
        }


class BeliefState:
    """Track belief state over time with Bayesian updating"""
    
    def __init__(self, initial_probability: float = 0.5):
        self.history = [{
            "probability": initial_probability,
            "timestamp": datetime.utcnow(),
            "evidence": []
        }]
        self.current = initial_probability
    
    def update(self, new_evidence: List[Evidence], engine: BayesianEngine) -> float:
        """Add evidence and update belief"""
        
        result = engine.update_probability(self.current, new_evidence)
        
        self.current = result.updated_probability
        self.history.append({
            "probability": result.updated_probability,
            "timestamp": datetime.utcnow(),
            "evidence": result.evidence_applied,
            "adjustment": result.total_adjustment
        })
        
        return self.current
    
    def get_trajectory(self) -> List[Dict]:
        """Get full belief trajectory"""
        return self.history
    
    def get_latest(self) -> float:
        """Get current probability"""
        return self.current
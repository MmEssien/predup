"""Edge Filter - Multi-condition betting decision logic"""

from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ConfidenceBand(Enum):
    VERY_HIGH = "very_high"
    HIGH = "high" 
    MEDIUM = "medium"
    LOW = "low"


class FilterReason(Enum):
    APPROVED = "approved"
    INSUFFICIENT_EDGE = "insufficient_edge"
    LOW_AGREEMENT = "low_agreement"
    HIGH_VARIANCE = "high_variance"
    LOW_CONFIDENCE = "low_confidence"
    MARKET_MISALIGNMENT = "market_misalignment"
    BELOW_THRESHOLD = "below_threshold"


@dataclass
class FilterResult:
    """Result of edge filtering"""
    approved: bool
    reason: FilterReason
    confidence_band: ConfidenceBand
    edge_score: float
    agreement_score: float
    variance_score: float
    final_probability: float
    details: Dict[str, Any]


class EdgeFilter:
    """Multi-condition edge filter for betting decisions"""
    
    def __init__(
        self,
        # Edge settings
        min_edge_absolute: float = 0.02,      # 2% absolute edge minimum
        min_edge_percentage: float = 0.05,     # 5% relative edge
        
        # Agreement settings
        min_agreement: float = 0.5,
        
        # Variance settings  
        max_variance: float = 0.08,
        
        # Confidence bands
        very_high_threshold: float = 0.70,
        high_threshold: float = 0.60,
        medium_threshold: float = 0.50,
        
        # Kelly settings
        kelly_fraction: float = 0.25,
        max_kelly: float = 0.02,
        
        # League overrides
        league_overrides: Optional[Dict[str, Dict]] = None
    ):
        self.min_edge_absolute = min_edge_absolute
        self.min_edge_percentage = min_edge_percentage
        self.min_agreement = min_agreement
        self.max_variance = max_variance
        
        self.very_high_threshold = very_high_threshold
        self.high_threshold = high_threshold
        self.medium_threshold = medium_threshold
        
        self.kelly_fraction = kelly_fraction
        self.max_kelly = max_kelly
        
        # League-specific overrides (updated to 0.70 based on analysis)
        self.league_overrides = league_overrides or {
            "BL1": {"min_edge": 0.05, "min_agreement": 0.55},
            "PL": {"min_edge": 0.05, "min_agreement": 0.55},
            "PD": {"min_edge": 0.05, "min_agreement": 0.60},
            "SA": {"min_edge": 0.05, "min_agreement": 0.60},
        }
    
    def should_bet(
        self,
        model_probability: float,
        market_odds: float,
        model_predictions: Dict[str, float],
        league_code: Optional[str] = None,
        market_implied: Optional[float] = None,
        variance: Optional[float] = None,
        agreement: Optional[float] = None
    ) -> FilterResult:
        """Determine if a bet should be placed based on multiple conditions"""
        
        # Get league-specific settings
        league_config = self.league_overrides.get(league_code, {})
        min_edge = league_config.get("min_edge", self.min_edge_absolute)
        min_agree = league_config.get("min_agreement", self.min_agreement)
        
        # Calculate or use provided values
        if market_implied is None:
            market_implied = 1 / market_odds if market_odds > 0 else 0
        
        if variance is None:
            variance = self._calculate_variance(model_predictions)
        
        if agreement is None:
            agreement = self._calculate_agreement(model_predictions)
        
        # Calculate edge
        edge_absolute = model_probability - market_implied
        edge_percentage = (edge_absolute / market_implied) if market_implied > 0 else 0
        
        # Determine confidence band
        confidence_band = self._get_confidence_band(model_probability, variance)
        
        # Apply confidence adjustment based on variance
        adjusted_prob = self._adjust_probability(model_probability, variance)
        
        # Multi-condition check
        reasons = []
        
        # Check 1: Minimum edge
        if edge_absolute < min_edge:
            reasons.append(FilterReason.INSUFFICIENT_EDGE)
        
        # Check 2: Model agreement
        if agreement < min_agree:
            reasons.append(FilterReason.LOW_AGREEMENT)
        
        # Check 3: Variance threshold
        if variance > self.max_variance:
            reasons.append(FilterReason.HIGH_VARIANCE)
        
        # Check 4: Confidence band (minimum threshold)
        if adjusted_prob < self.medium_threshold:
            reasons.append(FilterReason.LOW_CONFIDENCE)
        
        # Check 5: Market misalignment (model and market too far apart without justification)
        if abs(model_probability - market_implied) > 0.25:
            reasons.append(FilterReason.MARKET_MISALIGNMENT)
        
        # Determine final decision
        if not reasons:
            approved = True
            final_reason = FilterReason.APPROVED
        else:
            approved = False
            # Use the first failure reason (most critical)
            final_reason = reasons[0]
        
        return FilterResult(
            approved=approved,
            reason=final_reason,
            confidence_band=confidence_band,
            edge_score=edge_absolute,
            agreement_score=agreement,
            variance_score=variance,
            final_probability=adjusted_prob,
            details={
                "edge_absolute": edge_absolute,
                "edge_percentage": edge_percentage,
                "market_implied": market_implied,
                "league_config": league_config,
                "reasons_blocked": [r.value for r in reasons] if reasons else []
            }
        )
    
    def _calculate_variance(self, model_predictions: Dict[str, float]) -> float:
        """Calculate variance in model predictions"""
        if not model_predictions or len(model_predictions) < 2:
            return 0.0
        
        import numpy as np
        predictions = list(model_predictions.values())
        return float(np.var(predictions))
    
    def _calculate_agreement(self, model_predictions: Dict[str, float]) -> float:
        """Calculate agreement between models"""
        if not model_predictions or len(model_predictions) < 2:
            return 1.0
        
        import numpy as np
        predictions = list(model_predictions.values())
        mean_pred = np.mean(predictions)
        std_pred = np.std(predictions)
        
        # Agreement = 1 - normalized standard deviation
        agreement = 1.0 - min(std_pred * 2, 1.0)
        return float(agreement)
    
    def _get_confidence_band(self, probability: float, variance: float) -> ConfidenceBand:
        """Determine confidence band"""
        
        # Adjust threshold based on variance
        effective_threshold = self.very_high_threshold + variance * 0.5
        
        if probability >= effective_threshold:
            return ConfidenceBand.VERY_HIGH
        elif probability >= self.high_threshold + variance * 0.3:
            return ConfidenceBand.HIGH
        elif probability >= self.medium_threshold:
            return ConfidenceBand.MEDIUM
        else:
            return ConfidenceBand.LOW
    
    def _adjust_probability(self, probability: float, variance: float) -> float:
        """Adjust probability based on variance"""
        
        # High variance reduces confidence
        if variance > 0.10:
            return probability * 0.85
        elif variance > 0.05:
            return probability * 0.92
        else:
            return probability
    
    def calculate_kelly_stake(
        self,
        probability: float,
        odds: float,
        bankroll: float = 1000.0,
        confidence_adjustment: float = 1.0
    ) -> float:
        """Calculate Kelly stake with confidence adjustment"""
        
        if odds <= 1:
            return 0.0
        
        b = odds - 1
        p = probability
        q = 1 - p
        
        # Raw Kelly
        kelly = (b * p - q) / b
        
        # Apply fractional Kelly
        kelly = kelly * self.kelly_fraction * confidence_adjustment
        
        # Apply confidence adjustment to the kelly fraction
        # Higher confidence = higher fraction
        if confidence_adjustment > 1.0:
            kelly *= min(confidence_adjustment, 1.5)
        
        # Boundary checks
        kelly = max(0, kelly)
        kelly = min(kelly, self.max_kelly)
        
        return kelly * bankroll
    
    def get_stake_recommendation(
        self,
        model_probability: float,
        odds: float,
        bankroll: float = 1000.0,
        model_predictions: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        """Get complete stake recommendation with filtering"""
        
        variance = self._calculate_variance(model_predictions or {})
        agreement = self._calculate_agreement(model_predictions or {})
        
        # Get confidence adjustment from agreement
        confidence_adjustment = 0.8 + (agreement * 0.4)  # Range: 0.8 - 1.2
        
        # Filter check
        filter_result = self.should_bet(
            model_probability,
            odds,
            model_predictions or {}
        )
        
        if not filter_result.approved:
            return {
                "action": "NO_BET",
                "reason": filter_result.reason.value,
                "stake": 0,
                "filter_result": filter_result.details
            }
        
        # Calculate stake
        stake = self.calculate_kelly_stake(
            filter_result.final_probability,
            odds,
            bankroll,
            confidence_adjustment
        )
        
        # Expected value
        ev = (filter_result.final_probability * (odds - 1)) - ((1 - filter_result.final_probability))
        
        return {
            "action": "BET" if stake > 0 else "NO_BET",
            "reason": "approved",
            "stake": stake,
            "probability": filter_result.final_probability,
            "odds": odds,
            "expected_value": ev,
            "edge": filter_result.edge_score,
            "confidence_band": filter_result.confidence_band.value,
            "agreement": agreement,
            "variance": variance,
            "kelly_fraction": self.kelly_fraction * confidence_adjustment,
            "details": filter_result.details
        }
    
    def batch_filter(
        self,
        predictions: List[Dict[str, Any]],
        league_code: Optional[str] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Filter a batch of predictions"""
        
        accepted = []
        rejected = []
        
        for pred in predictions:
            result = self.should_bet(
                model_probability=pred.get("probability", 0),
                market_odds=pred.get("odds", 2.0),
                model_predictions=pred.get("model_predictions", {}),
                league_code=league_code
            )
            
            pred["filter_result"] = {
                "approved": result.approved,
                "reason": result.reason.value,
                "edge": result.edge_score,
                "agreement": result.agreement_score,
                "variance": result.variance_score
            }
            
            if result.approved:
                accepted.append(pred)
            else:
                rejected.append(pred)
        
        return {
            "accepted": accepted,
            "rejected": rejected,
            "stats": {
                "total": len(predictions),
                "accepted": len(accepted),
                "rejected": len(rejected),
                "acceptance_rate": len(accepted) / len(predictions) if predictions else 0
            }
        }
    
    def get_optimal_threshold(
        self,
        predictions: List[Dict[str, Any]],
        actuals: List[int],
        league_code: Optional[str] = None
    ) -> Dict[str, Any]:
        """Find optimal threshold for this filter configuration"""
        
        thresholds = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75]
        results = []
        
        original_threshold = self.medium_threshold
        
        for threshold in thresholds:
            self.medium_threshold = threshold
            
            correct = 0
            total = 0
            
            for pred, actual in zip(predictions, actuals):
                result = self.should_bet(
                    pred.get("probability", 0),
                    pred.get("odds", 2.0),
                    pred.get("model_predictions", {}),
                    league_code
                )
                
                if result.approved:
                    total += 1
                    predicted_value = 1 if pred.get("probability", 0) >= threshold else 0
                    if predicted_value == actual:
                        correct += 1
            
            if total > 0:
                results.append({
                    "threshold": threshold,
                    "total": total,
                    "correct": correct,
                    "accuracy": correct / total
                })
        
        # Restore original
        self.medium_threshold = original_threshold
        
        if not results:
            return {"optimal_threshold": 0.60, "best_accuracy": 0}
        
        best = max(results, key=lambda x: x["accuracy"])
        
        return {
            "optimal_threshold": best["threshold"],
            "best_accuracy": best["accuracy"],
            "all_results": results
        }
"""Fusion Engine - Market + Model Ensemble"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import logging
import numpy as np

logger = logging.getLogger(__name__)


class StrategyType(Enum):
    """Fusion strategy types"""
    MODEL_ONLY = "model_only"
    MARKET_ONLY = "market_only"
    WEIGHTED_AVERAGE = "weighted_average"
    ADAPTIVE = "adaptive"
    CONFIDENCE_WEIGHTED = "confidence_weighted"
    MARKET_REGRESSION = "market_regression"


@dataclass
class FusionResult:
    """Result of fusion process"""
    final_probability: float
    strategy_used: StrategyType
    ml_probability: float
    market_probability: float
    confidence: float
    agreement: float
    recommendation: str
    edge_estimate: float
    details: Dict[str, Any]


class FusionEngine:
    """Fuse ML predictions with market intelligence"""
    
    def __init__(
        self,
        # Weights for different components
        ml_weight: float = 0.6,
        market_weight: float = 0.3,
        momentum_weight: float = 0.1,
        
        # Strategy settings
        default_strategy: StrategyType = StrategyType.WEIGHTED_AVERAGE,
        
        # Confidence settings
        min_agreement_for_boost: float = 0.85,  # 85% agreement = boost
        confidence_boost_cap: float = 0.10,
        
        # Market regression settings
        market_regression_strength: float = 0.15,  # How much to regress to market
        max_divergence_for_confidence: float = 0.15
    ):
        self.ml_weight = ml_weight
        self.market_weight = market_weight
        self.momentum_weight = momentum_weight
        self.default_strategy = default_strategy
        
        self.min_agreement_for_boost = min_agreement_for_boost
        self.confidence_boost_cap = confidence_boost_cap
        
        self.market_regression_strength = market_regression_strength
        self.max_divergence_for_confidence = max_divergence_for_confidence
    
    def fuse(
        self,
        model_probability: float,
        market_implied: float,
        momentum_signal: float = 0.0,
        strategy: Optional[StrategyType] = None,
        market_signal: Optional[Dict] = None
    ) -> FusionResult:
        """Fuse model and market predictions"""
        
        if strategy is None:
            strategy = self.default_strategy
        
        if strategy == StrategyType.MODEL_ONLY:
            return self._model_only(model_probability, market_implied)
        
        elif strategy == StrategyType.MARKET_ONLY:
            return self._market_only(model_probability, market_implied)
        
        elif strategy == StrategyType.WEIGHTED_AVERAGE:
            return self._weighted_average(model_probability, market_implied, momentum_signal)
        
        elif strategy == StrategyType.ADAPTIVE:
            return self._adaptive_fusion(model_probability, market_implied, momentum_signal, market_signal)
        
        elif strategy == StrategyType.CONFIDENCE_WEIGHTED:
            return self._confidence_weighted(model_probability, market_implied, momentum_signal)
        
        elif strategy == StrategyType.MARKET_REGRESSION:
            return self._market_regression(model_probability, market_implied, market_signal)
        
        else:
            return self._weighted_average(model_probability, market_implied, momentum_signal)
    
    def _model_only(
        self,
        model_prob: float,
        market_implied: float
    ) -> FusionResult:
        """Use model only"""
        
        agreement = self._calculate_agreement(model_prob, market_implied)
        
        return FusionResult(
            final_probability=model_prob,
            strategy_used=StrategyType.MODEL_ONLY,
            ml_probability=model_prob,
            market_probability=market_implied,
            confidence=1.0 - abs(model_prob - 0.5),
            agreement=agreement,
            recommendation="bet" if model_prob > 0.55 else "pass",
            edge_estimate=model_prob - market_implied,
            details={"note": "Using model probability only"}
        )
    
    def _market_only(
        self,
        model_prob: float,
        market_implied: float
    ) -> FusionResult:
        """Use market only"""
        
        agreement = self._calculate_agreement(model_prob, market_implied)
        
        return FusionResult(
            final_probability=market_implied,
            strategy_used=StrategyType.MARKET_ONLY,
            ml_probability=model_prob,
            market_probability=market_implied,
            confidence=0.8,
            agreement=agreement,
            recommendation="pass" if market_implied > 0.5 else "pass",
            edge_estimate=0,
            details={"note": "Using market probability only"}
        )
    
    def _weighted_average(
        self,
        model_prob: float,
        market_implied: float,
        momentum: float
    ) -> FusionResult:
        """Simple weighted average fusion"""
        
        # Calculate normalized weights
        total_weight = self.ml_weight + self.market_weight + self.momentum_weight
        ml_w = self.ml_weight / total_weight
        market_w = self.market_weight / total_weight
        momentum_w = self.momentum_weight / total_weight
        
        # Apply weighted fusion
        fused = (
            ml_w * model_prob +
            market_w * market_implied +
            momentum_w * (0.5 + momentum * 0.5)  # Center momentum around 0.5
        )
        
        agreement = self._calculate_agreement(model_prob, market_implied)
        
        # Calculate confidence boost from agreement
        confidence_boost = 0
        if agreement >= self.min_agreement_for_boost:
            confidence_boost = min(
                (agreement - self.min_agreement_for_boost) * self.confidence_boost_cap * 2,
                self.confidence_boost_cap
            )
        
        base_confidence = 0.7
        confidence = min(base_confidence + confidence_boost, 1.0)
        
        return FusionResult(
            final_probability=fused,
            strategy_used=StrategyType.WEIGHTED_AVERAGE,
            ml_probability=model_prob,
            market_probability=market_implied,
            confidence=confidence,
            agreement=agreement,
            recommendation=self._get_recommendation(fused, confidence),
            edge_estimate=fused - market_implied,
            details={
                "weights": {"ml": ml_w, "market": market_w, "momentum": momentum_w},
                "confidence_boost": confidence_boost
            }
        )
    
    def _adaptive_fusion(
        self,
        model_prob: float,
        market_implied: float,
        momentum: float,
        market_signal: Optional[Dict]
    ) -> FusionResult:
        """Adaptive fusion based on market conditions"""
        
        agreement = self._calculate_agreement(model_prob, market_implied)
        divergence = abs(model_prob - market_implied)
        
        # Adjust weights based on conditions
        if market_signal:
            signal_type = market_signal.get("signal_type", "efficient")
            
            if signal_type == "mispricing":
                # Strong model edge - trust model more
                ml_w = 0.75
                market_w = 0.15
            elif signal_type == "sharp_money":
                # Sharp money signal - lean toward market
                ml_w = 0.40
                market_w = 0.50
            else:
                # Default
                ml_w = self.ml_weight
                market_w = self.market_weight
        else:
            # Adjust based on divergence
            if divergence > 0.15:
                # Significant divergence - trust model less until proven
                ml_w = 0.45
                market_w = 0.45
            else:
                ml_w = self.ml_weight
                market_w = self.market_weight
        
        # Normalize weights
        total = ml_w + market_w + self.momentum_weight
        ml_w /= total
        market_w /= total
        momentum_w = self.momentum_weight / total
        
        # Fuse
        fused = (
            ml_w * model_prob +
            market_w * market_implied +
            momentum_w * (0.5 + momentum * 0.5)
        )
        
        # Confidence based on agreement + signal quality
        confidence = min(agreement * 0.6 + 0.4, 1.0)
        
        return FusionResult(
            final_probability=fused,
            strategy_used=StrategyType.ADAPTIVE,
            ml_probability=model_prob,
            market_probability=market_implied,
            confidence=confidence,
            agreement=agreement,
            recommendation=self._get_recommendation(fused, confidence),
            edge_estimate=fused - market_implied,
            details={
                "adaptive_weights": {"ml": ml_w, "market": market_w, "momentum": momentum_w},
                "divergence": divergence
            }
        )
    
    def _confidence_weighted(
        self,
        model_prob: float,
        market_implied: float,
        momentum: float
    ) -> FusionResult:
        """Weight by confidence levels"""
        
        # Model confidence based on certainty
        model_confidence = 1.0 - abs(model_prob - 0.5) * 2
        
        # Market confidence based on bookmaker agreement
        market_confidence = 0.7  # Default market confidence
        
        # Total confidence
        total_conf = model_confidence + market_confidence
        ml_w = model_confidence / total_conf
        market_w = market_confidence / total_conf
        
        # Fuse
        fused = ml_w * model_prob + market_w * market_implied
        
        agreement = self._calculate_agreement(model_prob, market_implied)
        
        return FusionResult(
            final_probability=fused,
            strategy_used=StrategyType.CONFIDENCE_WEIGHTED,
            ml_probability=model_prob,
            market_probability=market_implied,
            confidence=min(model_confidence, 1.0),
            agreement=agreement,
            recommendation=self._get_recommendation(fused, model_confidence),
            edge_estimate=fused - market_implied,
            details={"model_confidence": model_confidence, "market_confidence": market_confidence}
        )
    
    def _market_regression(
        self,
        model_prob: float,
        market_implied: float,
        market_signal: Optional[Dict]
    ) -> FusionResult:
        """Regress toward market for high divergence scenarios"""
        
        divergence = abs(model_prob - market_implied)
        
        if divergence < self.max_divergence_for_confidence:
            # Small divergence - use model
            fused = model_prob
            strategy = "model_trust"
        elif divergence < self.max_divergence_for_confidence * 2:
            # Moderate divergence - blend
            regression_factor = (divergence - self.max_divergence_for_confidence) / self.max_divergence_for_confidence
            regression_factor *= self.market_regression_strength
            
            fused = model_prob * (1 - regression_factor) + market_implied * regression_factor
            strategy = "partial_regression"
        else:
            # Large divergence - follow market
            fused = market_implied
            strategy = "market_trust"
        
        agreement = self._calculate_agreement(model_prob, market_implied)
        
        return FusionResult(
            final_probability=fused,
            strategy_used=StrategyType.MARKET_REGRESSION,
            ml_probability=model_prob,
            market_probability=market_implied,
            confidence=1.0 - (divergence / 0.5),
            agreement=agreement,
            recommendation=self._get_recommendation(fused, 0.7),
            edge_estimate=fused - market_implied,
            details={"strategy": strategy, "divergence": divergence}
        )
    
    def _calculate_agreement(self, prob1: float, prob2: float) -> float:
        """Calculate agreement between probabilities (0-1)"""
        return 1.0 - min(abs(prob1 - prob2) * 2, 1.0)
    
    def _get_recommendation(self, probability: float, confidence: float) -> str:
        """Get betting recommendation"""
        
        if probability >= 0.60 and confidence >= 0.7:
            return "strong_back"
        elif probability >= 0.55 and confidence >= 0.6:
            return "back"
        elif probability <= 0.40 and confidence >= 0.7:
            return "strong_lay"
        elif probability <= 0.45 and confidence >= 0.6:
            return "lay"
        else:
            return "pass"
    
    def batch_fuse(
        self,
        predictions: List[Dict[str, Any]],
        strategy: Optional[StrategyType] = None
    ) -> List[FusionResult]:
        """Fuse a batch of predictions"""
        
        results = []
        
        for pred in predictions:
            model_prob = pred.get("probability", 0.5)
            market_odds = pred.get("odds", 2.0)
            market_implied = 1 / market_odds if market_odds > 0 else 0.5
            momentum = pred.get("momentum", 0.0)
            market_signal = pred.get("market_signal")
            
            result = self.fuse(
                model_prob, market_implied, momentum,
                strategy=strategy, market_signal=market_signal
            )
            
            results.append(result)
        
        return results
    
    def compare_strategies(
        self,
        model_probability: float,
        market_implied: float,
        momentum: float = 0.0
    ) -> Dict[str, FusionResult]:
        """Compare all fusion strategies"""
        
        strategies = [
            StrategyType.MODEL_ONLY,
            StrategyType.MARKET_ONLY,
            StrategyType.WEIGHTED_AVERAGE,
            StrategyType.ADAPTIVE,
            StrategyType.CONFIDENCE_WEIGHTED,
            StrategyType.MARKET_REGRESSION
        ]
        
        results = {}
        
        for strategy in strategies:
            results[strategy.value] = self.fuse(
                model_probability, market_implied, momentum, strategy
            )
        
        return results
    
    def get_optimal_fusion_params(
        self,
        historical_predictions: List[Dict],
        actuals: List[int]
    ) -> Dict[str, Any]:
        """Find optimal fusion parameters using backtesting"""
        
        best_params = {}
        best_accuracy = 0
        
        # Test different weight combinations
        ml_weights = [0.5, 0.6, 0.7, 0.8]
        market_weights = [0.2, 0.3, 0.4]
        
        for ml_w in ml_weights:
            for market_w in market_weights:
                total = ml_w + market_w
                if total >= 1.0:
                    continue
                
                momentum_w = 1.0 - total
                
                correct = 0
                total_bets = 0
                
                for pred, actual in zip(historical_predictions, actuals):
                    model_prob = pred.get("probability", 0.5)
                    market_odds = pred.get("odds", 2.0)
                    market_implied = 1 / market_odds if market_odds > 0 else 0.5
                    momentum = pred.get("momentum", 0.0)
                    
                    fused = (
                        ml_w * model_prob +
                        market_w * market_implied +
                        momentum_w * (0.5 + momentum * 0.5)
                    )
                    
                    predicted = 1 if fused >= 0.55 else 0
                    
                    if predicted in [0, 1]:
                        total_bets += 1
                        if predicted == actual:
                            correct += 1
                
                accuracy = correct / total_bets if total_bets > 0 else 0
                
                if accuracy > best_accuracy:
                    best_accuracy = accuracy
                    best_params = {
                        "ml_weight": ml_w,
                        "market_weight": market_w,
                        "momentum_weight": momentum_w,
                        "accuracy": accuracy
                    }
        
        return best_params
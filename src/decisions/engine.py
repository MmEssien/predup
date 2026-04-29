"""Decision engine for PredUp - League-Specialized with Intelligence Engine"""

import logging
import os
from typing import Dict, List, Optional, Any, Tuple
import numpy as np
import pandas as pd

from src.utils.helpers import load_config
from src.intelligence.edge_filter import EdgeFilter
from src.intelligence.kelly_advanced import AdvancedKelly
from src.intelligence.fusion_engine import FusionEngine
from src.intelligence.bayesian_engine import BayesianEngine
from src.intelligence.regime_detector import RegimeDetector
from src.intelligence.market_analyzer import MarketAnalyzer
from src.intelligence.feedback_loop import FeedbackLoop
from src.models.calibrator import LeagueCalibrator

logger = logging.getLogger(__name__)


# Final Production Configuration
# Validated with realistic odds and consistent performance

LEAGUE_CONFIGS = {
    # PRODUCTION - Confirmed positive ROI (consistent across splits)
    "BL1": {"competition_id": 7, "api_id": 78, "threshold": 0.70, "min_agreement": 0.5, "tier": 1, "status": "production"},
    "PL": {"competition_id": 3, "api_id": 39, "threshold": 0.50, "min_agreement": 0.5, "tier": 1, "status": "production"},
    
    # TESTING - Need more validation but promising
    "PD": {"competition_id": 12, "api_id": 140, "threshold": 0.35, "min_agreement": 0.55, "tier": 1, "status": "testing"},
    
    # PAUSED - Performance varies by data split (unstable)
    "SA": {"competition_id": 8, "api_id": 135, "threshold": 0.75, "min_agreement": 0.55, "tier": 1, "status": "paused"},
    "FL1": {"competition_id": 6, "api_id": 61, "threshold": 0.75, "min_agreement": 0.5, "tier": 1, "status": "paused"},
    
    # NO DATA - target_over_25 not available
    "ELC": {"competition_id": 2, "api_id": 41, "threshold": 0.70, "min_agreement": 0.55, "tier": 2, "status": "paused"},
    "ECD": {"competition_id": 9, "api_id": 88, "threshold": 0.70, "min_agreement": 0.55, "tier": 2, "status": "paused"},
    "POR": {"competition_id": 10, "api_id": 94, "threshold": 0.70, "min_agreement": 0.55, "tier": 2, "status": "paused"},
    "BSA": {"competition_id": 1, "api_id": 71, "threshold": 0.70, "min_agreement": 0.55, "tier": 2, "status": "paused"},
}

# Production enabled leagues
ENABLED_LEAGUES = ["BL1", "PL"]

# All configured leagues
ALL_LEAGUES = {
    "BL1": "production",
    "PL": "production",
    "PD": "testing",
    "SA": "paused",
    "FL1": "paused",
    "ELC": "paused",
    "ECD": "paused",
    "POR": "paused",
    "BSA": "paused",
}

# League tiers for trust levels
LEAGUE_TIERS = {
    1: {"name": "High Confidence", "min_edge": 0.03, "max_exposure": 0.15},
    2: {"name": "Moderate", "min_edge": 0.05, "max_exposure": 0.10},
    3: {"name": "Experimental", "min_edge": 0.08, "max_exposure": 0.05},
}

# Production enabled leagues (confirmed positive ROI)
ENABLED_LEAGUES = ["BL1", "PL"]

# All configured leagues with status
ALL_LEAGUES = {
    "BL1": "production",
    "PL": "production", 
    "PD": "testing",
    "SA": "testing",
    "FL1": "testing",
    "ELC": "paused",
    "ECD": "paused",
    "POR": "paused",
    "BSA": "paused",
}

# Production status mapping
LEAGUE_STATUS = {
    "BL1": "production",
    "PL": "production",
    "SA": "sandbox",
    "PD": "sandbox", 
    "FL1": "sandbox",
    "ELC": "paused",
    "ECD": "paused",
    "BEL": "paused",
    "LIG1": "paused",
    "LIG2": "paused",
}


class DecisionEngine:
    def __init__(self, config: Optional[Dict] = None, league_code: Optional[str] = None,
                 enable_intelligence: bool = True):
        self.config = config or {}
        self.league_code = league_code
        self.enable_intelligence = enable_intelligence
        self.min_confidence = self.config.get("min_confidence", 0.55)
        self.ensemble_weights = self.config.get("ensemble_weights", {
            "xgboost": 0.4,
            "lightgbm": 0.4,
            "logreg": 0.2,
        })
        
        # Intelligence engine components (initialized only if enable_intelligence=True)
        self._intelligence = None
        
        # League-specific overrides
        if league_code and league_code in LEAGUE_CONFIGS:
            league_conf = LEAGUE_CONFIGS[league_code]
            self.min_confidence = league_conf.get("threshold", self.min_confidence)
            self.min_agreement = league_conf.get("min_agreement", 0.5)
        else:
            self.min_agreement = 0.5
    
    @property
    def intelligence(self):
        """Lazy load intelligence components"""
        if self._intelligence is None and self.enable_intelligence:
            self._intelligence = IntelligenceEngine(self.league_code)
        return self._intelligence

    def make_advanced_decision(
        self,
        model_probability: float,
        market_odds: float,
        model_predictions: Dict[str, float],
        fixture_data: Optional[Dict[str, Any]] = None,
        odds_history: Optional[List[Dict]] = None,
       evidence: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        Make decision using full Intelligence Engine pipeline.
        
        This method runs the complete pipeline:
        1. Bayesian updating with evidence
        2. Fusion with market intelligence
        3. Regime detection
        4. Edge filtering
        5. Kelly stake calculation
        """
        if not self.enable_intelligence:
            # Fallback to basic decision
            is_accepted, confidence, decision = self.make_decision(
                model_probability, model_predictions
            )
            return {
                "approved": is_accepted,
                "confidence": confidence,
                "decision": decision,
                "probability": model_probability,
                "stake": 0,
                "reason": "intelligence_disabled"
            }
        
        intell = self.intelligence
        
        # Step 1: Bayesian update
        if evidence:
            bayes_result = intell.bayesian.update_from_events(
                model_probability, evidence, self.league_code
            )
            adjusted_prob = bayes_result.updated_probability
        else:
            adjusted_prob = model_probability
        
        # Step 2: Market fusion
        market_implied = 1 / market_odds if market_odds > 0 else 0.5
        fusion_result = intell.fusion.fuse(
            adjusted_prob, market_implied,
            momentum_signal=0.0,
            strategy=intell.fusion.default_strategy
        )
        
        # Step 3: Regime detection
        if fixture_data:
            regime_result = intell.detector.detect_regime(fixture_data)
            # Apply regime adjustment
            final_prob = intell.detector.apply_regime_adjustment(
                fusion_result.final_probability, regime_result
            )
        else:
            final_prob = fusion_result.final_probability
            regime_result = None
        
        # Step 4: Edge filter
        filter_result = intell.edge_filter.should_bet(
            final_prob,
            market_odds,
            model_predictions,
            self.league_code,
            market_implied=market_implied
        )
        
        # Step 5: Calculate stake
        stake_result = None
        if filter_result.approved:
            stake_result = intell.kelly.calculate_stake(
                filter_result.final_probability,
                market_odds,
                bankroll=self.config.get("bankroll", 10000),
                confidence=fusion_result.confidence
            )
            stake = stake_result.recommended_stake
        else:
            stake = 0
        
        # Generate recommendation
        recommendation = "PASS"
        if filter_result.approved and stake > 0:
            if filter_result.confidence_band.value in ["very_high", "high"]:
                recommendation = "STRONG_BET"
            else:
                recommendation = "BET"
        
        return {
            "approved": filter_result.approved,
            "confidence": fusion_result.confidence,
            "decision": "accept" if filter_result.approved else "reject",
            "reason": filter_result.reason.value,
            "probability": filter_result.final_probability,
            "original_probability": model_probability,
            "adjusted_probability": adjusted_prob,
            "fused_probability": fusion_result.final_probability,
            "market_implied": market_implied,
            "edge": filter_result.edge_score,
            "agreement": filter_result.agreement_score,
            "variance": filter_result.variance_score,
            "confidence_band": filter_result.confidence_band.value,
            "stake": stake if stake_result else 0,
            "stake_size": stake_result.stake_size.value if stake_result else "no_bet",
            "expected_value": stake_result.expected_value if stake_result else 0,
            "recommendation": recommendation,
            "regime": regime_result.regime_type.value if regime_result else "unknown",
            "regime_factors": regime_result.factors if regime_result else {},
            "fusion_details": fusion_result.details if hasattr(fusion_result, 'details') else {},
            "filter_details": filter_result.details
        }

    def make_decision(
        self,
        prediction: float,
        model_predictions: Dict[str, float],
        threshold: Optional[float] = None
    ) -> Tuple[bool, float, str]:
        """Make accept/reject decision on prediction - League Specialized"""
        threshold = threshold or self.min_confidence

        model_agreement = self._calculate_agreement(model_predictions)
        variance = self._calculate_variance(model_predictions)

        # Adjust confidence based on variance
        if variance > 0.1:
            confidence = prediction * 0.9
        else:
            confidence = prediction
        
        # League-specific minimum agreement
        min_agreement = self.min_agreement

        if confidence >= threshold and model_agreement >= min_agreement:
            decision = "accept"
        elif confidence >= threshold * 0.9:
            decision = "review"
        else:
            decision = "reject"

        is_accepted = decision == "accept"

        return is_accepted, confidence, decision

    def _calculate_agreement(self, model_predictions: Dict[str, float]) -> float:
        """Calculate agreement between models"""
        if len(model_predictions) < 2:
            return 1.0

        predictions = list(model_predictions.values())
        mean_pred = np.mean(predictions)
        std_pred = np.std(predictions)

        agreement = 1.0 - min(std_pred * 2, 1.0)

        return agreement

    def _calculate_variance(self, model_predictions: Dict[str, float]) -> float:
        """Calculate variance in model predictions"""
        if not model_predictions:
            return 0.0

        predictions = list(model_predictions.values())
        return float(np.var(predictions))

    def filter_predictions(
        self,
        predictions: List[Dict[str, Any]],
        threshold: Optional[float] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Filter predictions by confidence"""
        accepted = []
        rejected = []
        review = []

        for pred in predictions:
            is_accepted, confidence, decision = self.make_decision(
                pred["probability"],
                pred.get("model_predictions", {}),
                threshold
            )

            pred["confidence"] = confidence
            pred["is_accepted"] = is_accepted
            pred["decision"] = decision

            if decision == "accept":
                accepted.append(pred)
            elif decision == "review":
                review.append(pred)
            else:
                rejected.append(pred)

        return {
            "accepted": accepted,
            "rejected": rejected,
            "review": review,
        }

    def get_confidence_band(
        self,
        probability: float,
        model_predictions: Dict[str, float]
    ) -> str:
        """Get confidence band for probability"""
        variance = self._calculate_variance(model_predictions)

        if variance > 0.15:
            return "low"
        elif variance > 0.08:
            return "medium"
        else:
            return "high"

    def calculate_expected_value(
        self,
        probability: float,
        odds: float = 2.0,
        stake: float = 1.0
    ) -> float:
        """Calculate expected value of bet"""
        ev = probability * (odds - 1) - (1 - probability) * stake
        return ev
    
    def calculate_value_edge(
        self,
        model_probability: float,
        implicit_probability: float
    ) -> Dict[str, float]:
        """Calculate value edge based on model vs market implied probability"""
        # Edge: how much better our probability is vs market
        edge = model_probability - implicit_probability
        
        # Value percentage: relative edge
        value_pct = edge / implicit_probability if implicit_probability > 0 else 0
        
        # Is there value? (>5% edge typically considered valuable)
        has_value = edge > 0.05
        
        return {
            "edge": edge,
            "value_percentage": value_pct * 100,
            "has_value": has_value,
            "model_prob": model_probability,
            "market_prob": implicit_probability
        }
    
    def calculate_ev_with_odds(
        self,
        model_probability: float,
        odds_data: Dict[str, float],
        stake: float = 1.0
    ) -> Dict[str, Any]:
        """Calculate EV using odds data with value detection"""
        home_odds = odds_data.get("odds_home_implied", 2.0)
        draw_odds = odds_data.get("odds_draw_implied", 3.0)
        away_odds = odds_data.get("odds_away_implied", 2.0)
        overround = odds_data.get("market_overround", 1.0)
        
        # Fair probabilities (normalized)
        total = (1/home_odds if home_odds > 0 else 0) + \
                (1/draw_odds if draw_odds > 0 else 0) + \
                (1/away_odds if away_odds > 0 else 0)
        
        if total > 0:
            fair_home = (1/home_odds) / total
            fair_away = (1/away_odds) / total
        else:
            fair_home = fair_away = 0.33
        
        # Check value for over 2.5 goals prediction
        # Implied over 2.5 probability from overround
        implied_over = min(fair_home + fair_away * 0.3, 0.6)  # Rough estimate
        
        value_info = self.calculate_value_edge(model_probability, implied_over)
        
        # EV for over 2.5 at typical odds (2.0)
        ev = self.calculate_expected_value(model_probability, 2.0, stake)
        
        return {
            "has_value": value_info["has_value"],
            "edge": value_info["edge"],
            "value_pct": value_info["value_percentage"],
            "ev": ev,
            "recommendation": "BET" if (value_info["has_value"] and ev > 0) else "PASS",
            "market_overround": overround,
            "risk_adjusted_stake": max(0, min(stake * value_info["value_percentage"], stake * 2))
        }

    def optimize_threshold(
        self,
        predictions: List[Dict[str, Any]],
        actuals: List[int],
        thresholds: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        """Find optimal confidence threshold"""
        if thresholds is None:
            thresholds = [0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9]

        results = []

        for threshold in thresholds:
            correct = 0
            total = 0

            for pred, actual in zip(predictions, actuals):
                is_accepted, _, _ = self.make_decision(
                    pred["probability"],
                    pred.get("model_predictions", {}),
                    threshold
                )

                if is_accepted:
                    total += 1
                    if pred["predicted_value"] == actual:
                        correct += 1

            if total > 0:
                accuracy = correct / total
                results.append({
                    "threshold": threshold,
                    "total": total,
                    "correct": correct,
                    "accuracy": accuracy,
                })

        if not results:
            return {"optimal_threshold": 0.75, "best_accuracy": 0}

        best = max(results, key=lambda x: x["accuracy"])

        return {
            "optimal_threshold": best["threshold"],
            "best_accuracy": best["accuracy"],
            "all_results": results,
        }

    def ensemble_predictions(
        self,
        model_predictions: Dict[str, float]
    ) -> float:
        """Create ensemble prediction from multiple models"""
        ensemble = 0.0

        for model_name, weight in self.ensemble_weights.items():
            if model_name in model_predictions:
                ensemble += weight * model_predictions[model_name]

        return ensemble


class RiskManager:
    def __init__(self, max_daily_bets: int = 10, max_exposure: float = 100.0):
        self.max_daily_bets = max_daily_bets
        self.max_exposure = max_exposure
        self.daily_bets = 0
        self.daily_exposure = 0.0

    def can_place_bet(self, stake: float = 1.0) -> Tuple[bool, str]:
        """Check if bet can be placed"""
        if self.daily_bets >= self.max_daily_bets:
            return False, "max_daily_bets_exceeded"

        if self.daily_exposure + stake > self.max_exposure:
            return False, "max_exposure_exceeded"

        return True, "ok"

    def record_bet(self, stake: float = 1.0, won: bool = False):
        """Record bet result"""
        self.daily_bets += 1

        if not won:
            self.daily_exposure += stake

    def reset_daily(self):
        """Reset daily counters"""
        self.daily_bets = 0
        self.daily_exposure = 0.0


def create_decision_engine(config: Optional[Dict] = None, league_code: str = None,
                          enable_intelligence: bool = True) -> DecisionEngine:
    """Create decision engine with optional league specialization"""
    full_config = load_config()
    model_config = full_config.get("model", {})

    if config:
        model_config.update(config)

    return DecisionEngine(model_config, league_code=league_code, 
                         enable_intelligence=enable_intelligence)


class IntelligenceEngine:
    """Combined Intelligence Engine - wraps all intelligence components"""
    
    def __init__(self, league_code: Optional[str] = None, enable_calibration: bool = True,
                 calibration_dir: str = "models/calibrators"):
        self.league_code = league_code
        self.enable_calibration = enable_calibration
        self.calibration_dir = calibration_dir
        self._calibrator = None
        self._feedback_loop = None
        self._calibration_loaded = False
        self._calibration_info = {}
        
        # Initialize all components
        self.edge_filter = EdgeFilter(league_overrides={
            "BL1": {"min_edge": 0.05, "min_agreement": 0.55},
            "PL": {"min_edge": 0.05, "min_agreement": 0.55},
        })
        
        self.kelly = AdvancedKelly(
            fraction=0.25,
            max_kelly=0.02,
            league_limits={
                "BL1": 0.10,
                "PL": 0.15,
                "default": 0.08
            }
        )
        
        self.fusion = FusionEngine(
            ml_weight=0.6,
            market_weight=0.3,
            momentum_weight=0.1
        )
        
        self.bayesian = BayesianEngine(
            league_adjustments={
                "BL1": {"home_advantage": 0.06, "derby_unpredictable": True},
                "PL": {"home_advantage": 0.05, "derby_unpredictable": True},
            }
        )
        
        self.detector = RegimeDetector()
        
        self.market_analyzer = MarketAnalyzer()
        
        # Auto-load calibrators if directory exists
        self._try_load_calibration()
    
    def _try_load_calibration(self) -> None:
        """Attempt to load calibrators from disk at startup"""
        if not self.enable_calibration:
            return
            
        try:
            import os
            if os.path.exists(self.calibration_dir):
                self.load_calibrators(self.calibration_dir)
                logger.info(f"Loaded calibrators from {self.calibration_dir}")
        except Exception as e:
            logger.warning(f"Could not load calibrators: {e}")
    
    @property
    def calibrator(self) -> LeagueCalibrator:
        """Lazy-load calibrator"""
        if self._calibrator is None and self.enable_calibration:
            self._calibrator = LeagueCalibrator()
        return self._calibrator
    
    @property
    def feedback_loop(self) -> FeedbackLoop:
        """Lazy-load feedback loop"""
        if self._feedback_loop is None:
            self._feedback_loop = FeedbackLoop(min_samples_for_analysis=20)
        return self._feedback_loop
    
    def load_calibrators(self, directory: str) -> None:
        """Load calibrators from directory"""
        self.calibration_dir = directory
        self.calibrator.load_all(directory)
        self._calibration_loaded = True
        
        # Store info about loaded calibrators
        for league, cal in self.calibrator.calibrators.items():
            if cal.is_fitted:
                metrics = cal.get_calibration_metrics()
                self._calibration_info[league] = {
                    "ece": metrics.get("ece", 0),
                    "mce": metrics.get("mce", 0),
                    "n_bins": metrics.get("n_bins", 0)
                }
        
        if self.calibrator.global_calibrator.is_fitted:
            metrics = self.calibrator.global_calibrator.get_calibration_metrics()
            self._calibration_info["global"] = {
                "ece": metrics.get("ece", 0),
                "mce": metrics.get("mce", 0)
            }
    
    def save_calibrators(self, directory: Optional[str] = None) -> None:
        """Save calibrators to directory"""
        save_dir = directory or self.calibration_dir
        self.calibrator.save_all(save_dir)
    
    def get_calibration_info(self) -> Dict:
        """Get information about loaded calibrators"""
        return {
            "loaded": self._calibration_loaded,
            "calibrators": self._calibration_info,
            "leagues_with_calibration": list(self.calibrator.calibrators.keys()) if self._calibrator else [],
            "global_fitted": self.calibrator.global_calibrator.is_fitted if self._calibrator else False
        }
    
    def fit_calibrator(self, y_true: np.ndarray, y_prob: np.ndarray, 
                       league_code: Optional[str] = None) -> None:
        """Fit calibration on training data"""
        if self.enable_calibration and self._calibrator is not None:
            target_league = league_code or self.league_code
            if target_league:
                self._calibrator.fit_league(target_league, y_true, y_prob)
            else:
                self._calibrator.fit_global(y_true, y_prob)
    
    def apply_calibration(self, probability: float) -> float:
        """Apply calibration to probability"""
        if self.enable_calibration and self._calibrator is not None:
            # Try league-specific first, then global
            if self.league_code and self.league_code in self.calibrator.calibrators:
                return self._calibrator.transform(np.array([probability]), self.league_code)[0]
            elif self._calibrator.global_calibrator.is_fitted:
                return self._calibrator.transform(np.array([probability]), None)[0]
        return probability
    
    def calibrate_probabilities(self, probabilities: np.ndarray) -> np.ndarray:
        """Apply calibration to array of probabilities"""
        if self.enable_calibration and self._calibrator is not None:
            return self._calibrator.transform(probabilities)
        return probabilities
    
    def record_result(
        self,
        fixture_id: int,
        predicted_probability: float,
        actual_probability: float,
        predicted_value: int,
        actual_value: int,
        odds: float,
        regime: str = "regular",
        confidence_band: str = "medium"
    ) -> None:
        """Record a result to feedback loop"""
        self.feedback_loop.record_result(
            fixture_id=fixture_id,
            league_code=self.league_code or "UNKNOWN",
            predicted_probability=predicted_probability,
            actual_probability=actual_probability,
            predicted_value=predicted_value,
            actual_value=actual_value,
            odds=odds,
            regime=regime,
            confidence_band=confidence_band
        )
    
    def get_feedback_stats(self) -> Dict:
        """Get feedback loop statistics"""
        return self.feedback_loop.get_overall_stats()
    
    def get_retrain_recommendation(self) -> Dict:
        """Get recommendation for model retraining"""
        return self.feedback_loop.get_retrain_recommendation()
    
    def process_prediction(
        self,
        model_probability: float,
        market_odds: float,
        model_predictions: Dict[str, float],
        fixture_data: Optional[Dict[str, Any]] = None,
        evidence: Optional[List[Dict]] = None,
        odds_history: Optional[List[Dict]] = None,
        bankroll: float = 10000.0,
        apply_calibration: bool = True,
        lineup_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Full prediction pipeline processing.
        
        CALIBRATION PIPELINE:
        1. Raw model probability
        2. Apply calibration FIRST (all downstream calculations use calibrated prob)
        3. Bayesian update with evidence
        4. Market fusion
        5. Regime detection
        6. Edge filtering
        7. EV calculation and Kelly sizing (uses calibrated probability)
        8. Lineup adjustment (final probability check)
        
        Returns comprehensive decision with calibrated probabilities throughout.
        """
        # 0. RAW probability (before calibration)
        raw_probability = model_probability
        
        # 1. Apply calibration FIRST - all downstream calculations MUST use calibrated prob
        if apply_calibration:
            model_probability = self.apply_calibration(model_probability)
        
        # Track calibration state
        calibration_info = {
            "calibration_applied": apply_calibration and self._calibration_loaded,
            "calibration_source": None,
            "raw_probability": raw_probability,
            "calibrated_probability": model_probability
        }
        
        if self.league_code and self.league_code in self.calibrator.calibrators:
            calibration_info["calibration_source"] = f"league_{self.league_code}"
        elif self.calibrator.global_calibrator.is_fitted:
            calibration_info["calibration_source"] = "global"
        
        # 2. Get market implied probability
        market_implied = 1 / market_odds if market_odds > 0 else 0.5
        
        # 3. Bayesian update with evidence
        if evidence:
            bayes_result = self.bayesian.update_from_events(
                model_probability, evidence, self.league_code
            )
            adjusted_prob = bayes_result.updated_probability
            bayes_confidence = bayes_result.confidence
        else:
            adjusted_prob = model_probability
            bayes_confidence = 0.7
        
        # 4. Market analysis if odds history available
        market_signal = None
        if odds_history:
            market_signal = self.market_analyzer.analyze_market(
                adjusted_prob, odds_history
            )
        
        # 5. Fusion with market - uses CALIBRATED probability
        fusion_result = self.fusion.fuse(
            adjusted_prob,
            market_implied,
            momentum_signal=0.0,
            strategy=None,
            market_signal=market_signal.__dict__ if market_signal else None
        )
        
        # 6. Regime detection
        regime_result = None
        if fixture_data:
            regime_result = self.detector.detect_regime(fixture_data)
            final_prob = self.detector.apply_regime_adjustment(
                fusion_result.final_probability, regime_result
            )
        else:
            final_prob = fusion_result.final_probability
        
        # 7. Apply lineup/injury adjustments if available
        lineup_adjustment = 0.0
        if lineup_data:
            from src.intelligence.lineup_layer import LineupLayer
            lineup_layer = LineupLayer()
            adjustment = lineup_layer.calculate_adjustment(lineup_data)
            final_prob = np.clip(final_prob + adjustment, 0.01, 0.99)
            lineup_adjustment = adjustment
        
        # 8. Edge filtering
        filter_result = self.edge_filter.should_bet(
            final_prob,
            market_odds,
            model_predictions,
            self.league_code,
            market_implied=market_implied
        )
        
        # 9. Stake calculation - MUST use CALIBRATED probability for EV
        stake = 0
        stake_size = "no_bet"
        expected_value = 0
        
        if filter_result.approved:
            # ALL EV calculations use CALIBRATED probability
            kelly_result = self.kelly.calculate_stake(
                probability=filter_result.final_probability,  # This is calibrated
                odds=market_odds,
                bankroll=bankroll,
                confidence=fusion_result.confidence,
                league_code=self.league_code
            )
            stake = kelly_result.recommended_stake
            stake_size = kelly_result.stake_size.value
            expected_value = kelly_result.expected_value  # Uses calibrated probability
            
            # Additional EV check using calibrated probability
            ev_check = {
                "calibrated_prob": filter_result.final_probability,
                "market_prob": market_implied,
                "odds": market_odds,
                "ev_calculated": expected_value,
                "edge": kelly_result.edge
            }
        
        # Build response
        return {
            # Core decision
            "approved": filter_result.approved,
            "decision": "accept" if filter_result.approved else "reject",
            "reason": filter_result.reason.value,
            
            # Calibration chain
            "raw_probability": raw_probability,
            "probability": model_probability,  # CALIBRATED probability
            "calibration": calibration_info,
            
            # Probability flow (all calibrated)
            "adjusted_probability": adjusted_prob,
            "fused_probability": fusion_result.final_probability,
            "final_probability": filter_result.final_probability,
            "market_implied": market_implied,
            
            # Lineup adjustment
            "lineup_adjustment": lineup_adjustment,
            "lineup_adjusted_probability": final_prob,
            
            # Quality metrics
            "edge": filter_result.edge_score,
            "agreement": filter_result.agreement_score,
            "variance": filter_result.variance_score,
            "confidence": fusion_result.confidence,
            "confidence_band": filter_result.confidence_band.value,
            
            # Bet details - ALL based on CALIBRATED probability
            "stake": stake,
            "stake_size": stake_size,
            "odds": market_odds,
            "expected_value": expected_value,
            
            # Context
            "regime": regime_result.regime_type.value if regime_result else "regular",
            "regime_unpredictability": regime_result.unpredictability_score if regime_result else 0.3,
            "is_derby": regime_result.is_derby if regime_result else False,
            
            # Market
            "market_signal": market_signal.signal_type.value if market_signal else "unknown",
            "market_recommendation": market_signal.recommended_action if market_signal else "pass",
            
            # All details
            "filter_details": filter_result.details,
            "fusion_details": fusion_result.details if hasattr(fusion_result, 'details') else {},
        }
    
    def batch_process(
        self,
        predictions: List[Dict[str, Any]],
        bankroll: float = 10000.0
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Process multiple predictions"""
        
        accepted = []
        rejected = []
        
        for pred in predictions:
            result = self.process_prediction(
                model_probability=pred.get("probability", 0.5),
                market_odds=pred.get("odds", 2.0),
                model_predictions=pred.get("model_predictions", {}),
                fixture_data=pred.get("fixture_data"),
                evidence=pred.get("evidence"),
                odds_history=pred.get("odds_history"),
                bankroll=bankroll
            )
            
            if result["approved"]:
                accepted.append(result)
            else:
                rejected.append(result)
        
        return {
            "accepted": accepted,
            "rejected": rejected,
            "stats": {
                "total": len(predictions),
                "accepted": len(accepted),
                "rejected": len(rejected),
                "acceptance_rate": len(accepted) / len(predictions) if predictions else 0,
                "total_stake": sum(a["stake"] for a in accepted)
            }
        }
    
    def settle_prediction(
        self,
        prediction_result: Dict[str, Any],
        actual_value: int,
        actual_probability: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Settle a prediction with the actual outcome.
        
        This records the result to the feedback loop for ongoing analysis.
        """
        if not prediction_result.get("approved"):
            return {"status": "no_bet_placed", "message": "No bet was placed on this prediction"}
        
        # Calculate actual outcome
        predicted_value = 1 if prediction_result.get("probability", 0) >= 0.5 else 0
        
        # Default actual_probability to actual_value if not provided
        if actual_probability is None:
            actual_probability = float(actual_value)
        
        # Record to feedback loop
        self.feedback_loop.record_result(
            fixture_id=prediction_result.get("fixture_id", 0),
            league_code=self.league_code or "UNKNOWN",
            predicted_probability=prediction_result.get("probability", 0.5),
            actual_probability=actual_probability,
            predicted_value=predicted_value,
            actual_value=actual_value,
            odds=prediction_result.get("odds", 2.0),
            regime=prediction_result.get("regime", "regular"),
            confidence_band=prediction_result.get("confidence_band", "medium")
        )
        
        # Calculate profit
        is_correct = predicted_value == actual_value
        odds = prediction_result.get("odds", 2.0)
        stake = prediction_result.get("stake", 0)
        
        profit = 0
        if is_correct:
            profit = stake * (odds - 1)
        elif stake > 0:
            profit = -stake
        
        return {
            "status": "settled",
            "is_correct": is_correct,
            "profit": profit,
            "predicted_value": predicted_value,
            "actual_value": actual_value,
            "feedback_stats": self.feedback_loop.get_overall_stats()
        }


def is_league_enabled(league_code: str) -> bool:
    """Check if a league is enabled for betting"""
    return league_code in ENABLED_LEAGUES


def get_league_threshold(league_code: str) -> float:
    """Get optimal threshold for a specific league"""
    return LEAGUE_CONFIGS.get(league_code, {}).get("threshold", 0.55)


def filter_by_league(fixtures: List[Dict], enabled_leagues: List[str] = None) -> List[Dict]:
    """Filter fixtures to only include enabled leagues"""
    if enabled_leagues is None:
        enabled_leagues = ENABLED_LEAGUES
    
    return [f for f in fixtures if f.get("competition_code") in enabled_leagues]


def get_league_recommendation(league_code: str, confidence: float, ev: float) -> Dict[str, Any]:
    """Get betting recommendation based on league configuration"""
    if not is_league_enabled(league_code):
        return {"action": "SKIP", "reason": "League disabled", "stake": 0}
    
    threshold = get_league_threshold(league_code)
    
    if confidence < threshold:
        return {"action": "SKIP", "reason": f"Below threshold ({threshold})", "stake": 0}
    
    if ev < 0:
        return {"action": "SKIP", "reason": "Negative EV", "stake": 0}
    
    # Calculate stake using Kelly
    kelly = KellyCriterion(fraction=0.25, max_kelly=0.02)
    stake = kelly.calculate_stake(confidence, 2.0)  # Assume 2.0 odds
    
    return {
        "action": "BET",
        "confidence": confidence,
        "expected_value": ev,
        "stake": stake,
        "threshold": threshold,
    }
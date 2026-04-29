"""Advanced Kelly Criterion with Portfolio Management"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import logging
import numpy as np

logger = logging.getLogger(__name__)


class StakeSize(Enum):
    NO_BET = "no_bet"
    TINY = "tiny"      # < 0.5% bankroll
    SMALL = "small"    # 0.5-1% bankroll
    MEDIUM = "medium"  # 1-2% bankroll
    LARGE = "large"    # 2-3% bankroll
    MAX = "max"        # > 3% bankroll


@dataclass
class KellyResult:
    """Result of Kelly calculation"""
    raw_kelly: float
    fractional_kelly: float
    adjusted_kelly: float
    recommended_stake: float
    stake_size: StakeSize
    edge: float
    expected_value: float
    confidence_factor: float


class AdvancedKelly:
    """Advanced Kelly Criterion with portfolio-level stake allocation"""
    
    def __init__(
        self,
        fraction: float = 0.25,          # Fractional Kelly (0.25 = quarter Kelly)
        max_kelly: float = 0.02,         # Maximum 2% of bankroll per bet
        min_kelly: float = 0.001,        # Minimum 0.1% to bet
        confidence_weight: bool = True,  # Adjust by confidence
        league_limits: Optional[Dict[str, float]] = None,  # Per-league max exposure
        correlation_adjustment: bool = True  # Reduce for correlated bets
    ):
        self.fraction = fraction
        self.max_kelly = max_kelly
        self.min_kelly = min_kelly
        self.confidence_weight = confidence_weight
        self.correlation_adjustment = correlation_adjustment
        
        # Default league limits (max % per league)
        self.league_limits = league_limits or {
            "BL1": 0.10,    # 10% max exposure to Bundesliga
            "PL": 0.15,     # 15% max exposure to Premier League
            "default": 0.08
        }
    
    def calculate_stake(
        self,
        probability: float,
        odds: float,
        bankroll: float = 1000.0,
        confidence: float = 1.0,
        league_code: Optional[str] = None
    ) -> KellyResult:
        """Calculate optimal stake using Kelly criterion"""
        
        if odds <= 1 or probability <= 0 or probability >= 1:
            return self._empty_result()
        
        # B = odds - 1 (decimal odds conversion)
        b = odds - 1
        p = probability
        q = 1 - p
        
        # Raw Kelly formula: f* = (bp - q) / b
        raw_kelly = (b * p - q) / b
        
        # Apply fractional Kelly
        fractional_kelly = raw_kelly * self.fraction
        
        # Apply confidence adjustment
        if self.confidence_weight and confidence < 1.0:
            confidence_factor = 0.7 + (confidence * 0.3)  # Range: 0.7 - 1.0
        else:
            confidence_factor = 1.0
        
        adjusted_kelly = fractional_kelly * confidence_factor
        
        # Apply league limit
        league_limit = self.league_limits.get(league_code, self.league_limits["default"])
        adjusted_kelly = min(adjusted_kelly, league_limit)
        
        # Apply global max
        adjusted_kelly = min(adjusted_kelly, self.max_kelly)
        
        # Floor at min_kelly or 0
        if adjusted_kelly < self.min_kelly:
            adjusted_kelly = 0
        
        # Calculate stake
        recommended_stake = adjusted_kelly * bankroll
        
        # Determine stake size category
        stake_pct = adjusted_kelly
        stake_size = self._categorize_stake(stake_pct)
        
        # Calculate edge and EV
        edge = probability - (1 / odds)
        expected_value = (probability * (odds - 1)) - (1 - probability)
        
        return KellyResult(
            raw_kelly=raw_kelly,
            fractional_kelly=fractional_kelly,
            adjusted_kelly=adjusted_kelly,
            recommended_stake=recommended_stake,
            stake_size=stake_size,
            edge=edge,
            expected_value=expected_value,
            confidence_factor=confidence_factor
        )
    
    def _empty_result(self) -> KellyResult:
        """Return empty result for invalid inputs"""
        return KellyResult(
            raw_kelly=0,
            fractional_kelly=0,
            adjusted_kelly=0,
            recommended_stake=0,
            stake_size=StakeSize.NO_BET,
            edge=0,
            expected_value=0,
            confidence_factor=0
        )
    
    def _categorize_stake(self, kelly_pct: float) -> StakeSize:
        """Categorize stake size"""
        if kelly_pct <= 0:
            return StakeSize.NO_BET
        elif kelly_pct < 0.005:
            return StakeSize.TINY
        elif kelly_pct < 0.01:
            return StakeSize.SMALL
        elif kelly_pct < 0.02:
            return StakeSize.MEDIUM
        elif kelly_pct < 0.03:
            return StakeSize.LARGE
        else:
            return StakeSize.MAX
    
    def calculate_portfolio_allocation(
        self,
        predictions: List[Dict[str, Any]],
        bankroll: float = 1000.0,
        max_total_exposure: float = 0.15,  # Max 15% of bankroll across all bets
        correlation_factor: float = 0.5    # How correlated bets are (0-1)
    ) -> List[Dict[str, Any]]:
        """Allocate stakes across multiple predictions with portfolio-level limits"""
        
        if not predictions:
            return []
        
        # First pass: calculate individual stakes
        results = []
        total_kelly = 0
        
        for pred in predictions:
            result = self.calculate_stake(
                probability=pred.get("probability", 0.5),
                odds=pred.get("odds", 2.0),
                bankroll=bankroll,
                confidence=pred.get("confidence", 1.0),
                league_code=pred.get("league_code")
            )
            
            results.append({
                **pred,
                "kelly_result": result,
                "individual_stake": result.recommended_stake
            })
            
            total_kelly += result.adjusted_kelly
        
        # Cap total exposure
        if total_kelly > max_total_exposure:
            scale_factor = max_total_exposure / total_kelly
            logger.info(f"Portfolio cap applied: scaling all stakes by {scale_factor:.2f}")
            
            for r in results:
                r["scaled_stake"] = r["individual_stake"] * scale_factor
                r["scaled_kelly"] = r["kelly_result"].adjusted_kelly * scale_factor
        else:
            for r in results:
                r["scaled_stake"] = r["individual_stake"]
                r["scaled_kelly"] = r["kelly_result"].adjusted_kelly
        
        # Sort by edge (highest first)
        results.sort(key=lambda x: x.get("kelly_result", {}).edge or 0, reverse=True)
        
        # Apply correlation adjustment if enabled
        if self.correlation_adjustment and len(results) > 1:
            for i, r in enumerate(results):
                if i > 0:  # Not the highest edge
                    # Reduce stake for correlated (lower edge) bets
                    corr_reduction = 1 - (correlation_factor * 0.3)
                    r["scaled_stake"] *= corr_reduction
                    r["scaled_kelly"] *= corr_reduction
        
        return results
    
    def get_bet_sizing_matrix(
        self,
        probabilities: List[float],
        odds: float,
        bankroll: float = 1000.0
    ) -> List[KellyResult]:
        """Calculate stake sizing for multiple probabilities"""
        
        return [
            self.calculate_stake(p, odds, bankroll)
            for p in probabilities
        ]
    
    def simulate_roi(
        self,
        predictions: List[Dict[str, Any]],
        actuals: List[int],
        bankroll: float = 1000.0,
        n_simulations: int = 1000
    ) -> Dict[str, float]:
        """Simulate ROI with Kelly betting"""
        
        if len(predictions) != len(actuals):
            raise ValueError("Predictions and actuals must have same length")
        
        results = []
        
        for _ in range(n_simulations):
            bank = bankroll
            for pred, actual in zip(predictions, actuals):
                kelly = self.calculate_stake(
                    pred["probability"],
                    pred.get("odds", 2.0),
                    bank
                )
                
                if kelly.recommended_stake > 0:
                    stake = kelly.recommended_stake
                    if pred["predicted_value"] == actual:
                        bank += stake * (pred["odds"] - 1)
                    else:
                        bank -= stake
            
            results.append((bank - bankroll) / bankroll * 100)
        
        return {
            "mean_roi": np.mean(results),
            "median_roi": np.median(results),
            "std_roi": np.std(results),
            "min_roi": np.min(results),
            "max_roi": np.max(results),
            "positive_roi_pct": sum(1 for r in results if r > 0) / len(results) * 100
        }
    
    def get_recommendation(self, probability: float, odds: float) -> str:
        """Get simple recommendation string"""
        result = self.calculate_stake(probability, odds)
        
        if result.stake_size == StakeSize.NO_BET:
            return "NO BET"
        elif result.stake_size == StakeSize.TINY:
            return "TINY"
        elif result.stake_size == StakeSize.SMALL:
            return "SMALL"
        elif result.stake_size == StakeSize.MEDIUM:
            return "MEDIUM"
        elif result.stake_size == StakeSize.LARGE:
            return "LARGE"
        else:
            return "MAX"


class PortfolioManager:
    """Manage portfolio-level betting"""
    
    def __init__(
        self,
        initial_bankroll: float = 10000.0,
        max_daily_bets: int = 10,
        max_league_exposure: float = 0.20,  # 20% per league
        max_single_bet: float = 0.05        # 5% max single bet
    ):
        self.initial_bankroll = initial_bankroll
        self.current_bankroll = initial_bankroll
        self.max_daily_bets = max_daily_bets
        self.max_league_exposure = max_league_exposure
        self.max_single_bet = max_single_bet
        
        self.daily_bets = 0
        self.league_exposure = {}
        self.active_bets = []
    
    def can_bet(
        self,
        stake: float,
        league_code: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Check if bet can be placed"""
        
        # Daily limit
        if self.daily_bets >= self.max_daily_bets:
            return False, "max_daily_bets"
        
        # Single bet limit
        if stake / self.current_bankroll > self.max_single_bet:
            return False, "max_single_bet"
        
        # League exposure
        if league_code:
            current_exposure = self.league_exposure.get(league_code, 0)
            new_exposure = current_exposure + (stake / self.current_bankroll)
            
            if new_exposure > self.max_league_exposure:
                return False, "max_league_exposure"
        
        # Total bankroll
        if stake > self.current_bankroll:
            return False, "insufficient_bankroll"
        
        return True, "ok"
    
    def place_bet(
        self,
        stake: float,
        league_code: Optional[str] = None,
        odds: float = 2.0,
        predicted_value: int = 1
    ) -> bool:
        """Place a bet and update tracking"""
        
        can_bet, reason = self.can_bet(stake, league_code)
        
        if not can_bet:
            logger.info(f"Bet rejected: {reason}")
            return False
        
        self.daily_bets += 1
        
        if league_code:
            self.league_exposure[league_code] = self.league_exposure.get(league_code, 0) + stake
        
        self.active_bets.append({
            "stake": stake,
            "odds": odds,
            "league": league_code,
            "predicted_value": predicted_value,
            "potential_return": stake * (odds - 1) if predicted_value == 1 else -stake
        })
        
        self.current_bankroll -= stake
        
        return True
    
    def settle_bet(
        self,
        won: bool,
        odds: float = 2.0
    ) -> float:
        """Settle the last bet"""
        
        if not self.active_bets:
            return 0
        
        bet = self.active_bets.pop()
        
        if won:
            self.current_bankroll += bet["stake"] * odds
            return bet["stake"] * (odds - 1)
        else:
            return -bet["stake"]
    
    def get_portfolio_stats(self) -> Dict[str, Any]:
        """Get current portfolio statistics"""
        
        return {
            "current_bankroll": self.current_bankroll,
            "initial_bankroll": self.initial_bankroll,
            "total_return": self.current_bankroll - self.initial_bankroll,
            "roi_pct": (self.current_bankroll - self.initial_bankroll) / self.initial_bankroll * 100,
            "daily_bets": self.daily_bets,
            "remaining_bets": self.max_daily_bets - self.daily_bets,
            "league_exposure": self.league_exposure,
            "active_bets": len(self.active_bets)
        }
    
    def reset_daily(self):
        """Reset daily counters"""
        self.daily_bets = 0
        self.league_exposure = {}
    
    def reset_all(self):
        """Reset everything"""
        self.current_bankroll = self.initial_bankroll
        self.reset_daily()
        self.active_bets = []
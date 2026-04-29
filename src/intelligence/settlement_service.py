"""Auto-Settlement Service

Automatically resolves predictions after matches finish.
Stores outcomes, CLV, calibration drift, and updates feedback loop.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import numpy as np
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class SettlementStatus(Enum):
    PENDING = "pending"
    SETTLED = "settled"
    NO_BET = "no_bet"
    ERROR = "error"


@dataclass
class SettlementResult:
    """Result of settling a prediction"""
    fixture_id: int
    status: SettlementStatus
    predicted_value: int
    actual_value: int
    is_correct: bool
    odds: float
    stake: float
    profit: float
    clv: float
    clv_percentage: float
    calibration_drift: float
    settled_at: datetime
    message: str


class AutoSettlementService:
    """
    Automatically settles predictions and updates feedback loop.
    
    Workflow:
    1. Find pending predictions for completed fixtures
    2. Fetch actual results from API
    3. Calculate CLV (Closing Line Value)
    4. Store settlement and profit
    5. Update feedback loop
    6. Track calibration drift
    """
    
    def __init__(self, db_session: Session, feedback_loop=None):
        self.db = db_session
        self.feedback_loop = feedback_loop
        
    def settle_prediction(
        self,
        fixture_id: int,
        prediction_data: Dict[str, Any],
        actual_result: Dict[str, Any]
    ) -> SettlementResult:
        """
        Settle a single prediction.
        
        Args:
            fixture_id: The fixture ID
            prediction_data: Prediction data including probability, odds, stake
            actual_result: Actual match result with home_score, away_score, status
        """
        try:
            # Check if there's a bet placed
            if not prediction_data.get("is_accepted") or prediction_data.get("stake", 0) <= 0:
                return SettlementResult(
                    fixture_id=fixture_id,
                    status=SettlementStatus.NO_BET,
                    predicted_value=0,
                    actual_value=0,
                    is_correct=False,
                    odds=0,
                    stake=0,
                    profit=0,
                    clv=0,
                    clv_percentage=0,
                    calibration_drift=0,
                    settled_at=datetime.utcnow(),
                    message="No bet placed on this prediction"
                )
            
            # Determine predicted value
            predicted_prob = prediction_data.get("probability", 0.5)
            predicted_value = 1 if predicted_prob >= 0.5 else 0
            
            # Determine actual value from match result
            actual_value = self._calculate_actual_value(actual_result)
            
            # Check if prediction was correct
            is_correct = predicted_value == actual_value
            
            # Calculate profit
            odds = prediction_data.get("odds", 2.0)
            stake = prediction_data.get("stake", 0)
            
            if is_correct:
                profit = stake * (odds - 1)
            else:
                profit = -stake
            
            # Calculate CLV (Closing Line Value)
            clv, clv_percentage = self._calculate_clv(
                prediction_data.get("probability", 0.5),
                prediction_data.get("closing_odds", odds),
                actual_value
            )
            
            # Calculate calibration drift
            calibration_drift = self._calculate_calibration_drift(
                predicted_prob,
                actual_value
            )
            
            # Record to feedback loop
            if self.feedback_loop:
                self.feedback_loop.record_result(
                    fixture_id=fixture_id,
                    league_code=prediction_data.get("league_code", "UNKNOWN"),
                    predicted_probability=predicted_prob,
                    actual_probability=float(actual_value),
                    predicted_value=predicted_value,
                    actual_value=actual_value,
                    odds=odds,
                    regime=prediction_data.get("regime", "regular"),
                    confidence_band=prediction_data.get("confidence_band", "medium")
                )
            
            return SettlementResult(
                fixture_id=fixture_id,
                status=SettlementStatus.SETTLED,
                predicted_value=predicted_value,
                actual_value=actual_value,
                is_correct=is_correct,
                odds=odds,
                stake=stake,
                profit=profit,
                clv=clv,
                clv_percentage=clv_percentage,
                calibration_drift=calibration_drift,
                settled_at=datetime.utcnow(),
                message="Settled successfully"
            )
            
        except Exception as e:
            logger.error(f"Error settling prediction for fixture {fixture_id}: {e}")
            return SettlementResult(
                fixture_id=fixture_id,
                status=SettlementStatus.ERROR,
                predicted_value=0,
                actual_value=0,
                is_correct=False,
                odds=0,
                stake=0,
                profit=0,
                clv=0,
                clv_percentage=0,
                calibration_drift=0,
                settled_at=datetime.utcnow(),
                message=f"Error: {str(e)}"
            )
    
    def _calculate_actual_value(self, result: Dict[str, Any]) -> int:
        """Calculate actual outcome value from match result"""
        home_score = result.get("home_score", 0)
        away_score = result.get("away_score", 0)
        total_goals = home_score + away_score
        
        # For over 2.5 goals prediction
        return 1 if total_goals > 2 else 0
    
    def _calculate_clv(
        self,
        predicted_prob: float,
        closing_odds: float,
        actual_value: int
    ) -> Tuple[float, float]:
        """
        Calculate Closing Line Value (CLV).
        
        CLV = predicted_prob - closing_implied_prob
        CLV% = (CLV / closing_implied_prob) * 100
        
        Positive CLV means our prediction beat the closing line.
        """
        if closing_odds <= 0:
            return 0, 0
        
        closing_implied = 1 / closing_odds
        clv = predicted_prob - closing_implied
        clv_percentage = (clv / closing_implied * 100) if closing_implied > 0 else 0
        
        return clv, clv_percentage
    
    def _calculate_calibration_drift(
        self,
        predicted_prob: float,
        actual_value: int
    ) -> float:
        """
        Calculate calibration drift.
        
        Drift = actual_probability - predicted_probability
        
        Positive drift means predictions were under-confident.
        """
        return float(actual_value) - predicted_prob
    
    def settle_batch(
        self,
        predictions: List[Dict[str, Any]],
        results: Dict[int, Dict[str, Any]]
    ) -> List[SettlementResult]:
        """Settle multiple predictions"""
        settlements = []
        
        for pred in predictions:
            fixture_id = pred.get("fixture_id")
            
            if fixture_id in results:
                result = self.settle_prediction(
                    fixture_id=fixture_id,
                    prediction_data=pred,
                    actual_result=results[fixture_id]
                )
            else:
                result = SettlementResult(
                    fixture_id=fixture_id,
                    status=SettlementStatus.ERROR,
                    predicted_value=0,
                    actual_value=0,
                    is_correct=False,
                    odds=0,
                    stake=0,
                    profit=0,
                    clv=0,
                    clv_percentage=0,
                    calibration_drift=0,
                    settled_at=datetime.utcnow(),
                    message="No actual result available"
                )
            
            settlements.append(result)
        
        return settlements
    
    def get_settlement_summary(
        self,
        settlements: List[SettlementResult]
    ) -> Dict[str, Any]:
        """Get summary of settlement results"""
        
        settled = [s for s in settlements if s.status == SettlementStatus.SETTLED]
        no_bet = [s for s in settlements if s.status == SettlementStatus.NO_BET]
        errors = [s for s in settlements if s.status == SettlementStatus.ERROR]
        
        if not settled:
            return {
                "total": len(settlements),
                "settled": 0,
                "no_bet": len(no_bet),
                "errors": len(errors),
                "message": "No predictions to settle"
            }
        
        # Calculate aggregate metrics
        total_profit = sum(s.profit for s in settled)
        total_stake = sum(s.stake for s in settled)
        roi = (total_profit / total_stake * 100) if total_stake > 0 else 0
        
        win_count = sum(1 for s in settled if s.is_correct)
        win_rate = (win_count / len(settled) * 100) if settled else 0
        
        avg_clv = np.mean([s.clv for s in settled]) if settled else 0
        avg_calibration_drift = np.mean([s.calibration_drift for s in settled]) if settled else 0
        
        return {
            "total": len(settlements),
            "settled": len(settled),
            "no_bet": len(no_bet),
            "errors": len(errors),
            "profit": total_profit,
            "stake": total_stake,
            "roi": roi,
            "wins": win_count,
            "losses": len(settled) - win_count,
            "win_rate": win_rate,
            "avg_clv": avg_clv,
            "clv_positive_pct": sum(1 for s in settled if s.clv > 0) / len(settled) * 100 if settled else 0,
            "avg_calibration_drift": avg_calibration_drift,
            "settled_at": datetime.utcnow().isoformat()
        }
    
    def update_prediction_record(
        self,
        fixture_id: int,
        settlement: SettlementResult
    ) -> None:
        """Update PredictionRecord with settlement data"""
        from src.data.database import PredictionRecord
        
        record = self.db.query(PredictionRecord).filter(
            PredictionRecord.fixture_id == fixture_id
        ).first()
        
        if record:
            record.actual_outcome = "win" if settlement.is_correct else "loss"
            record.is_correct = settlement.is_correct
            record.profit = settlement.profit
            record.clv = settlement.clv
            record.clv_percentage = settlement.clv_percentage
            record.settled_at = settlement.settled_at
            
            self.db.commit()
        else:
            logger.warning(f"No PredictionRecord found for fixture {fixture_id}")
    
    def get_pending_settlements(
        self,
        hours_before_check: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Get predictions pending settlement where match has finished.
        
        Args:
            hours_before_check: Hours before match start to check for settlement
        """
        from src.data.database import Fixture, PredictionRecord
        
        cutoff = datetime.utcnow() - timedelta(hours=hours_before_check)
        
        pending = self.db.query(PredictionRecord).filter(
            PredictionRecord.settled_at.is_(None),
            PredictionRecord.is_accepted == True
        ).join(Fixture).filter(
            Fixture.utc_date < cutoff,
            Fixture.status == "FINISHED"
        ).all()
        
        return [self._record_to_dict(r) for r in pending]
    
    def _record_to_dict(self, record) -> Dict[str, Any]:
        """Convert record to dict"""
        return {
            "id": record.id,
            "fixture_id": record.fixture_id,
            "predicted_probability": record.predicted_probability,
            "predicted_odds": record.predicted_odds,
            "odds": record.market_odds_at_prediction,
            "stake": record.stake_fraction,
            "league_code": getattr(record, "league_code", "UNKNOWN"),
            "confidence_band": record.confidence_band,
            "regime": getattr(record, "regime", "regular"),
            "closing_odds": record.closing_odds
        }


class SettlementScheduler:
    """
    Scheduler for automatic settlement jobs.
    
    Runs periodically to:
    1. Check for completed matches
    2. Settle pending predictions
    3. Generate reports
    """
    
    def __init__(self, db_session: Session):
        self.db = db_session
        self.settlement_service = AutoSettlementService(db_session)
        
    def run_settlement_cycle(
        self,
        api_client,
        days_back: int = 1,
        days_forward: int = 0
    ) -> Dict[str, Any]:
        """
        Run a complete settlement cycle.
        
        1. Fetch completed fixtures
        2. Get pending predictions
        3. Settle each one
        4. Return summary
        """
        from src.data.database import Fixture
        
        # Find recently completed fixtures
        end_date = datetime.utcnow() + timedelta(days=days_forward)
        start_date = datetime.utcnow() - timedelta(days=days_back)
        
        completed = self.db.query(Fixture).filter(
            Fixture.status == "FINISHED",
            Fixture.utc_date >= start_date,
            Fixture.utc_date <= end_date
        ).all()
        
        results = {}
        for fixture in completed:
            results[fixture.id] = {
                "home_score": fixture.home_score,
                "away_score": fixture.away_score,
                "status": fixture.status
            }
        
        # Get pending predictions
        pending = self.settlement_service.get_pending_settlements()
        
        # Filter to our completed fixtures
        relevant_pending = [p for p in pending if p["fixture_id"] in results]
        
        # Settle all
        settlements = self.settlement_service.settle_batch(relevant_pending, results)
        
        # Update records
        for settlement in settlements:
            if settlement.status == SettlementStatus.SETTLED:
                self.settlement_service.update_prediction_record(
                    settlement.fixture_id,
                    settlement
                )
        
        # Get summary
        summary = self.settlement_service.get_settlement_summary(settlements)
        
        return {
            "fixtures_processed": len(completed),
            "predictions_settled": summary.get("settled", 0),
            "summary": summary
        }
    
    def schedule_daily(self) -> None:
        """Schedule daily settlement job (for cron/background scheduler)"""
        # This would be called by a scheduler like APScheduler
        # For now, just a marker for where to hook in
        pass


def create_settlement_record(
    db: Session,
    fixture_id: int,
    predicted_probability: float,
    predicted_odds: float,
    market_odds: float,
    model_version_id: int,
    is_accepted: bool,
    stake_fraction: float,
    league_code: str = None,
    edge_score: float = None,
    agreement_score: float = None,
    variance_score: float = None,
    confidence_band: str = None,
    closing_odds: float = None
) -> int:
    """Create a new prediction record for settlement tracking"""
    from src.data.database import PredictionRecord
    
    implied_prob = 1 / market_odds if market_odds > 0 else 0.5
    closing_implied = 1 / closing_odds if closing_odds else None
    
    record = PredictionRecord(
        fixture_id=fixture_id,
        model_version_id=model_version_id,
        predicted_probability=predicted_probability,
        predicted_odds=predicted_odds,
        prediction_type="over_25",
        market_odds_at_prediction=market_odds,
        market_bookmaker="unknown",
        closing_odds=closing_odds,
        implied_probability=implied_prob,
        closing_implied=closing_implied,
        clv=predicted_probability - closing_implied if closing_implied else 0,
        edge_score=edge_score,
        agreement_score=agreement_score,
        variance_score=variance_score,
        confidence_band=confidence_band,
        is_accepted=is_accepted,
        stake_fraction=stake_fraction,
        predicted_at=datetime.utcnow()
    )
    
    if league_code:
        record.league_code = league_code
    
    db.add(record)
    db.commit()
    
    return record.id
"""CLV (Closing Line Value) Tracker for PredUp"""

from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import logging

from sqlalchemy.orm import Session

from src.data.database import PredictionRecord, OddsHistory, OddsData, Fixture

logger = logging.getLogger(__name__)


@dataclass
class CLVResult:
    """Result of CLV calculation"""
    fixture_id: int
    prediction_type: str
    predicted_prob: float
    predicted_odds: float
    market_odds: float
    closing_odds: Optional[float]
    implied_prob: float
    closing_implied: Optional[float]
    clv: Optional[float]
    clv_pct: Optional[float]


class CLVTracker:
    """Track Closing Line Value for predictions"""

    # Sharp bookmakers for closing odds
    SHARP_BOOKMAKERS = ["pinnacle", "bet365", "williamhill", "unibet", "bwin"]
    
    def __init__(self, session: Session):
        self.session = session

    def record_prediction(
        self,
        fixture_id: int,
        predicted_probability: float,
        predicted_odds: float,
        market_odds: float,
        prediction_type: str = "home_win",
        model_version_id: Optional[int] = None,
        edge_score: Optional[float] = None,
        agreement_score: Optional[float] = None,
        variance_score: Optional[float] = None,
        confidence_band: str = "medium",
        bookmaker: str = "pinnacle"
    ) -> PredictionRecord:
        """Record a prediction with market odds for later CLV calculation"""
        
        # Calculate implied probability from market odds
        implied_prob = 1 / market_odds if market_odds > 0 else 0
        
        record = PredictionRecord(
            fixture_id=fixture_id,
            model_version_id=model_version_id,
            predicted_probability=predicted_probability,
            predicted_odds=predicted_odds,
            prediction_type=prediction_type,
            market_odds_at_prediction=market_odds,
            market_bookmaker=bookmaker,
            implied_probability=implied_prob,
            edge_score=edge_score,
            agreement_score=agreement_score,
            variance_score=variance_score,
            confidence_band=confidence_band,
            predicted_at=datetime.utcnow()
        )
        
        self.session.add(record)
        self.session.commit()
        
        logger.info(f"Recorded prediction for fixture {fixture_id}: prob={predicted_probability:.3f}, odds={market_odds:.2f}")
        
        return record

    def fetch_closing_odds(self, fixture_id: int, prediction_type: str = "home_win") -> Optional[Dict[str, float]]:
        """Fetch closing odds for a fixture after match has started/finished"""
        
        # Get the latest odds from sharp bookmakers
        latest_odds = self.session.query(OddsData).filter(
            OddsData.fixture_id == fixture_id,
            OddsData.bookmaker.in_(self.SHARP_BOOKMAKERS)
        ).order_by(OddsData.fetched_at.desc()).first()
        
        if not latest_odds:
            logger.warning(f"No closing odds found for fixture {fixture_id}")
            return None
        
        odds_map = {
            "home_win": latest_odds.home_odds,
            "draw": latest_odds.draw_odds,
            "away_win": latest_odds.away_odds
        }
        
        return {
            "odds": odds_map.get(prediction_type),
            "bookmaker": latest_odds.bookmaker,
            "fetched_at": latest_odds.fetched_at
        }

    def calculate_clv(self, prediction_record: PredictionRecord) -> Optional[CLVResult]:
        """Calculate CLV for a settled prediction"""
        
        closing = self.fetch_closing_odds(prediction_record.fixture_id, prediction_record.prediction_type)
        
        if not closing or not closing.get("odds"):
            return None
        
        closing_odds = closing["odds"]
        closing_implied = 1 / closing_odds if closing_odds > 0 else 0
        
        # CLV = predicted probability - closing implied probability
        clv = prediction_record.predicted_probability - closing_implied
        clv_pct = (clv / closing_implied * 100) if closing_implied > 0 else 0
        
        # Update the record
        prediction_record.closing_odds = closing_odds
        prediction_record.closing_bookmaker = closing["bookmaker"]
        prediction_record.closing_implied = closing_implied
        prediction_record.clv = clv
        prediction_record.clv_percentage = clv_pct
        prediction_record.closing_fetched_at = closing["fetched_at"]
        
        self.session.commit()
        
        return CLVResult(
            fixture_id=prediction_record.fixture_id,
            prediction_type=prediction_record.prediction_type,
            predicted_prob=prediction_record.predicted_probability,
            predicted_odds=prediction_record.predicted_odds,
            market_odds=prediction_record.market_odds_at_prediction,
            closing_odds=closing_odds,
            implied_prob=prediction_record.implied_probability,
            closing_implied=closing_implied,
            clv=clv,
            clv_pct=clv_pct
        )

    def settle_prediction(
        self,
        fixture_id: int,
        actual_outcome: str,
        profit: float = 0.0
    ) -> Optional[PredictionRecord]:
        """Settle a prediction with actual outcome"""
        
        record = self.session.query(PredictionRecord).filter(
            PredictionRecord.fixture_id == fixture_id,
            PredictionRecord.settled_at.is_(None)
        ).first()
        
        if not record:
            logger.warning(f"No unsettled prediction found for fixture {fixture_id}")
            return None
        
        record.actual_outcome = actual_outcome
        record.profit = profit
        record.settled_at = datetime.utcnow()
        
        # Determine if prediction was correct
        if actual_outcome == record.prediction_type:
            record.is_correct = True
        
        self.session.commit()
        
        # Calculate CLV
        self.calculate_clv(record)
        
        return record

    def get_clv_stats(self, league_code: Optional[str] = None) -> Dict[str, Any]:
        """Get CLV statistics"""
        
        query = self.session.query(PredictionRecord).filter(
            PredictionRecord.clv.isnot(None)
        )
        
        records = query.all()
        
        if not records:
            return {
                "total_predictions": 0,
                "avg_clv": 0,
                "positive_clv_pct": 0,
                "roi_estimate": 0
            }
        
        clvs = [r.clv for r in records if r.clv is not None]
        profits = [r.profit for r in records if r.profit is not None]
        
        total_profit = sum(profits)
        total_staked = len(profits) * 10  # Assume 10 units per bet
        
        return {
            "total_predictions": len(records),
            "avg_clv": sum(clvs) / len(clvs) if clvs else 0,
            "positive_clv_pct": sum(1 for c in clvs if c > 0) / len(clvs) * 100 if clvs else 0,
            "clv_std": (sum((c - sum(clvs)/len(clvs))**2 for c in clvs) / len(clvs)) ** 0.5 if len(clvs) > 1 else 0,
            "roi_estimate": (total_profit / total_staked * 100) if total_staked > 0 else 0,
            "total_profit": total_profit,
            "total_bets": len(profits)
        }

    def track_odds_movement(self, fixture_id: int) -> Optional[Dict[str, Any]]:
        """Track odds movement for a fixture"""
        
        history = self.session.query(OddsHistory).filter(
            OddsHistory.fixture_id == fixture_id
        ).order_by(OddsHistory.fetched_at).all()
        
        if len(history) < 2:
            return None
        
        first = history[0]
        last = history[-1]
        
        movement = {}
        
        if first.home_odds and last.home_odds:
            movement["home_pct"] = ((last.home_odds - first.home_odds) / first.home_odds) * 100
        
        if first.away_odds and last.away_odds:
            movement["away_pct"] = ((last.away_odds - first.away_odds) / first.away_odds) * 100
        
        movement["first_odds"] = {"home": first.home_odds, "away": first.away_odds}
        movement["last_odds"] = {"home": last.home_odds, "away": last.away_odds}
        movement["observation_count"] = len(history)
        
        return movement

    def find_positive_clv_predictions(self, min_clv: float = 0.02) -> List[PredictionRecord]:
        """Find predictions with positive CLV"""
        
        return self.session.query(PredictionRecord).filter(
            PredictionRecord.clv >= min_clv,
            PredictionRecord.clv.isnot(None)
        ).all()
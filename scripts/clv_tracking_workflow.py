"""
CLV Tracking Workflow

Enables Closing Line Value (CLV) tracking for predictions.
CLV = Model Probability - Closing Implied Probability

Usage:
    python scripts/clv_tracking_workflow.py
    
Workflow:
1. Record prediction with market odds at time of prediction
2. After match starts, fetch closing odds
3. Calculate CLV when settled
4. Analyze which predictions have positive CLV
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from datetime import datetime, timedelta
import numpy as np
import pandas as pd

from src.data.connection import DatabaseManager
from src.data.database import PredictionRecord, OddsData, Fixture
from sqlalchemy import func

db_manager = DatabaseManager.get_instance()
db_manager.initialize()


def record_prediction(
    fixture_id: int,
    predicted_probability: float,
    predicted_odds: float,
    market_odds: float,
    model_version_id: int = None,
    league_code: str = "BL1"
) -> PredictionRecord:
    """Record a prediction with market odds for later CLV calculation"""
    
    with db_manager.session() as session:
        implied_prob = 1 / market_odds if market_odds > 0 else 0
        
        record = PredictionRecord(
            fixture_id=fixture_id,
            model_version_id=model_version_id,
            predicted_probability=predicted_probability,
            predicted_odds=predicted_odds,
            prediction_type="over_25",
            market_odds_at_prediction=market_odds,
            market_bookmaker="pinnacle",
            implied_probability=implied_prob,
            edge_score=predicted_probability - implied_prob,
            predicted_at=datetime.utcnow()
        )
        
        session.add(record)
        session.commit()
        
        print(f"Recorded prediction for fixture {fixture_id}: prob={predicted_probability:.3f}, odds={market_odds:.2f}")
        
        return record


def fetch_closing_odds(fixture_id: int) -> dict:
    """Fetch latest odds for a fixture (simulates closing odds)"""
    
    with db_manager.session() as session:
        # Get latest odds from sharp bookmakers
        sharp_books = ['pinnacle', 'bet365', 'williamhill']
        
        odds = session.query(OddsData).filter(
            OddsData.fixture_id == fixture_id,
            OddsData.bookmaker.in_(sharp_books)
        ).order_by(OddsData.fetched_at.desc()).first()
        
        if odds:
            return {
                'home_odds': odds.home_odds,
                'away_odds': odds.away_odds,
                'bookmaker': odds.bookmaker,
                'fetched_at': odds.fetched_at
            }
        
        return None


def calculate_clv(prediction_record_id: int) -> dict:
    """Calculate CLV for a prediction record"""
    
    with db_manager.session() as session:
        record = session.query(PredictionRecord).filter(
            PredictionRecord.id == prediction_record_id
        ).first()
        
        if not record:
            return {'error': 'Record not found'}
        
        # Get closing odds
        closing = fetch_closing_odds(record.fixture_id)
        
        if not closing or not closing.get('home_odds'):
            return {'error': 'No closing odds available', 'status': 'pending'}
        
        closing_odds = closing['home_odds']
        closing_implied = 1 / closing_odds if closing_odds > 0 else 0
        
        # Calculate CLV
        clv = record.predicted_probability - closing_implied
        clv_pct = (clv / closing_implied * 100) if closing_implied > 0 else 0
        
        # Update record
        record.closing_odds = closing_odds
        record.closing_bookmaker = closing['bookmaker']
        record.closing_implied = closing_implied
        record.clv = clv
        record.clv_percentage = clv_pct
        record.closing_fetched_at = closing['fetched_at']
        
        session.commit()
        
        return {
            'status': 'calculated',
            'clv': clv,
            'clv_pct': clv_pct,
            'predicted_prob': record.predicted_probability,
            'closing_implied': closing_implied
        }


def settle_prediction(fixture_id: int, actual_outcome: str, profit: float):
    """Settle a prediction"""
    
    with db_manager.session() as session:
        record = session.query(PredictionRecord).filter(
            PredictionRecord.fixture_id == fixture_id,
            PredictionRecord.settled_at.is_(None)
        ).first()
        
        if not record:
            print(f"No unsettled prediction for fixture {fixture_id}")
            return None
        
        record.actual_outcome = actual_outcome
        record.profit = profit
        record.settled_at = datetime.utcnow()
        
        if actual_outcome == record.prediction_type:
            record.is_correct = True
        
        session.commit()
        
        # Calculate CLV if closing odds available
        clv_result = calculate_clv(record.id)
        
        return {'record': record, 'clv': clv_result}


def get_clv_stats() -> pd.DataFrame:
    """Get CLV statistics"""
    
    with db_manager.session() as session:
        records = session.query(PredictionRecord).filter(
            PredictionRecord.clv.isnot(None)
        ).all()
        
        if not records:
            return pd.DataFrame()
        
        data = [{
            'fixture_id': r.fixture_id,
            'predicted_prob': r.predicted_probability,
            'implied_prob': r.implied_probability,
            'closing_implied': r.closing_implied,
            'clv': r.clv,
            'clv_pct': r.clv_percentage,
            'is_correct': r.is_correct,
            'profit': r.profit
        } for r in records]
        
        df = pd.DataFrame(data)
        
        # Calculate summary stats
        summary = {
            'total_predictions': len(df),
            'positive_clv': (df['clv'] > 0).sum(),
            'avg_clv': df['clv'].mean(),
            'avg_clv_pct': df['clv_pct'].mean(),
            'win_rate': df['is_correct'].mean() * 100,
            'roi': (df['profit'].sum() / len(df)) * 100
        }
        
        return df, summary


def demo_clv_tracking():
    """Demonstrate CLV tracking workflow"""
    
    print("="*60)
    print("  CLV TRACKING DEMONSTRATION")
    print("="*60)
    
    # First check if we have prediction records
    with db_manager.session() as session:
        count = session.query(PredictionRecord).count()
        print(f"\nPrediction records in database: {count}")
    
    # Check if we have odds data
    with db_manager.session() as session:
        odds_count = session.query(OddsData).count()
        print(f"Odds records in database: {odds_count}")
    
    if count == 0:
        print("\n[INFO] No prediction records yet.")
        print("        In production, predictions are recorded with:")
        print("        - predicted_probability: Model's probability")
        print("        - market_odds_at_prediction: Odds when prediction made")
        print("        - implied_probability: Market's implied probability")
        
        print("\n        After match, closing odds are fetched and CLV is calculated:")
        print("        - CLV = predicted_probability - closing_implied")
        print("        - Positive CLV = beating the closing line")
        
        # Show a sample calculation
        print("\n        Example CLV calculation:")
        print("        - Your prediction: 65% probability")
        print("        - Market at close: Implied 55% (odds 1.82)")
        print("        - CLV = 0.65 - 0.55 = +10% (you had 10% edge)")
        
    return count > 0


if __name__ == "__main__":
    demo_clv_tracking()
    
    # Check for any existing CLV data
    try:
        df, summary = get_clv_stats()
        if summary:
            print("\n[CLV Statistics]:")
            print(f"  Total: {summary['total_predictions']}")
            print(f"  Positive CLV: {summary['positive_clv']}")
            print(f"  Avg CLV: {summary['avg_clv']:.3f}")
            print(f"  Avg CLV %: {summary['avg_clv_pct']:.1f}%")
            print(f"  Win Rate: {summary['win_rate']:.1f}%")
            print(f"  ROI: {summary['roi']:+.2f}%")
    except:
        pass
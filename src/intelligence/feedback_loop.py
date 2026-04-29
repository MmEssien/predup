"""
Feedback Loop System

Enables the system to learn from prediction outcomes:
1. Track prediction results
2. Analyze what went wrong
3. Identify patterns in misses
4. Suggest model retraining triggers
5. Update calibration based on recent performance

Usage:
    from src.intelligence.feedback_loop import FeedbackLoop
    
    feedback = FeedbackLoop()
    feedback.record_result(prediction_data, actual_outcome)
    feedback.analyze_misses()
    feedback.get_retrain_recommendation()
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict


class PredictionResult:
    """Single prediction result for tracking"""
    
    def __init__(
        self,
        fixture_id: int,
        league_code: str,
        predicted_probability: float,
        actual_probability: float,
        predicted_value: int,
        actual_value: int,
        odds: float,
        model_version: str = "v1",
        regime: str = "regular",
        confidence_band: str = "medium"
    ):
        self.fixture_id = fixture_id
        self.league_code = league_code
        self.predicted_probability = predicted_probability
        self.actual_probability = actual_probability
        self.predicted_value = predicted_value
        self.actual_value = actual_value
        self.odds = odds
        self.model_version = model_version
        self.regime = regime
        self.confidence_band = confidence_band
        
        self.is_correct = predicted_value == actual_value
        self.profit = self._calculate_profit()
        self.timestamp = datetime.utcnow()
    
    def _calculate_profit(self) -> float:
        if self.predicted_value == 0:
            return 0  # No bet placed
        if self.is_correct:
            return self.odds - 1
        return -1


class FeedbackLoop:
    """
    Feedback Loop System
    
    Tracks prediction history, analyzes patterns in misses,
    and provides recommendations for model updates.
    """
    
    def __init__(
        self,
        min_samples_for_analysis: int = 20,
        miss_threshold_for_alert: float = 0.15  # Alert if miss rate > 15% above expected
    ):
        self.results: List[PredictionResult] = []
        self.min_samples = min_samples_for_analysis
        self.miss_threshold = miss_threshold_for_alert
    
    def record_result(
        self,
        fixture_id: int,
        league_code: str,
        predicted_probability: float,
        actual_probability: float,
        predicted_value: int,
        actual_value: int,
        odds: float,
        model_version: str = "v1",
        regime: str = "regular",
        confidence_band: str = "medium"
    ) -> PredictionResult:
        """Record a prediction result"""
        
        result = PredictionResult(
            fixture_id=fixture_id,
            league_code=league_code,
            predicted_probability=predicted_probability,
            actual_probability=actual_probability,
            predicted_value=predicted_value,
            actual_value=actual_value,
            odds=odds,
            model_version=model_version,
            regime=regime,
            confidence_band=confidence_band
        )
        
        self.results.append(result)
        return result
    
    def analyze_by_confidence_band(self) -> pd.DataFrame:
        """Analyze performance by confidence band"""
        
        if len(self.results) < self.min_samples:
            return pd.DataFrame()
        
        df = self._to_dataframe()
        
        if df.empty:
            return pd.DataFrame()
        
        results = df.groupby('confidence_band').agg({
            'is_correct': ['count', 'sum', 'mean'],
            'profit': 'sum',
            'predicted_probability': 'mean',
            'actual_probability': 'mean'
        }).reset_index()
        
        results.columns = ['Band', 'N', 'Wins', 'WinRate', 'Profit', 'Avg_Pred_Prob', 'Avg_Actual_Prob']
        results['WinRate'] = results['WinRate'] * 100
        
        # Calibration error
        results['Calibration_Error'] = results['WinRate'] - (results['Avg_Pred_Prob'] * 100)
        
        return results
    
    def analyze_by_league(self) -> pd.DataFrame:
        """Analyze performance by league"""
        
        if len(self.results) < self.min_samples:
            return pd.DataFrame()
        
        df = self._to_dataframe()
        
        if df.empty:
            return pd.DataFrame()
        
        results = df.groupby('league_code').agg({
            'is_correct': ['count', 'sum', 'mean'],
            'profit': 'sum'
        }).reset_index()
        
        results.columns = ['League', 'N', 'Wins', 'WinRate', 'Profit']
        results['WinRate'] = results['WinRate'] * 100
        results['ROI'] = (results['Profit'] / results['N']) * 100
        
        return results
    
    def analyze_by_regime(self) -> pd.DataFrame:
        """Analyze performance by match regime"""
        
        if len(self.results) < self.min_samples:
            return pd.DataFrame()
        
        df = self._to_dataframe()
        
        if df.empty:
            return pd.DataFrame()
        
        results = df.groupby('regime').agg({
            'is_correct': ['count', 'sum', 'mean'],
            'profit': 'sum'
        }).reset_index()
        
        results.columns = ['Regime', 'N', 'Wins', 'WinRate', 'Profit']
        results['WinRate'] = results['WinRate'] * 100
        
        return results
    
    def analyze_misses(self) -> Dict:
        """Analyze patterns in missed predictions"""
        
        if len(self.results) < self.min_samples:
            return {'status': 'insufficient_data', 'message': f'Need {self.min_samples} samples'}
        
        df = self._to_dataframe()
        misses = df[df['is_correct'] == False]
        
        if len(misses) == 0:
            return {'status': 'no_misses', 'message': 'Perfect prediction record!'}
        
        analysis = {
            'total_misses': len(misses),
            'total_predictions': len(df),
            'miss_rate': len(misses) / len(df) * 100,
            'miss_analysis': {}
        }
        
        # Misses by confidence band
        miss_by_band = misses.groupby('confidence_band').size()
        analysis['miss_analysis']['by_confidence_band'] = miss_by_band.to_dict()
        
        # Misses by league
        miss_by_league = misses.groupby('league_code').size()
        analysis['miss_analysis']['by_league'] = miss_by_league.to_dict()
        
        # Misses by regime
        miss_by_regime = misses.groupby('regime').size()
        analysis['miss_analysis']['by_regime'] = miss_by_regime.to_dict()
        
        # Check for systematic issues
        issues = []
        
        # High miss rate in certain bands?
        band_analysis = self.analyze_by_confidence_band()
        if not band_analysis.empty:
            high_error_bands = band_analysis[abs(band_analysis['Calibration_Error']) > 10]
            if len(high_error_bands) > 0:
                issues.append({
                    'type': 'calibration_error',
                    'description': f"High calibration error in bands: {high_error_bands['Band'].tolist()}"
                })
        
        # League underperforming?
        league_analysis = self.analyze_by_league()
        if not league_analysis.empty:
            underperforming = league_analysis[league_analysis['WinRate'] < 50]
            if len(underperforming) > 0:
                issues.append({
                    'type': 'league_underperformance',
                    'description': f"Underperforming leagues: {underperforming['League'].tolist()}"
                })
        
        analysis['issues'] = issues
        
        return analysis
    
    def get_retrain_recommendation(self) -> Dict:
        """Get recommendation for when to retrain model"""
        
        if len(self.results) < self.min_samples:
            return {
                'action': 'WAIT',
                'reason': f'Insufficient data ({len(self.results)}/{self.min_samples})',
                'priority': 'low'
            }
        
        # Check for calibration issues
        band_analysis = self.analyze_by_confidence_band()
        
        if not band_analysis.empty:
            max_error = band_analysis['Calibration_Error'].abs().max()
            
            if max_error > 15:
                return {
                    'action': 'RETRAIN_CALIBRATION',
                    'reason': f'Severe calibration error detected: {max_error:.1f}%',
                    'priority': 'high',
                    'details': band_analysis.to_dict()
                }
            elif max_error > 10:
                return {
                    'action': 'RETRAIN_CALIBRATION',
                    'reason': f'Moderate calibration error: {max_error:.1f}%',
                    'priority': 'medium',
                    'details': band_analysis.to_dict()
                }
        
        # Check for league-specific issues
        league_analysis = self.analyze_by_league()
        
        if not league_analysis.empty:
            underperforming = league_analysis[league_analysis['WinRate'] < 45]
            if len(underperforming) > 0:
                return {
                    'action': 'INVESTIGATE_LEAGUE',
                    'reason': f'League underperformance: {underperforming["League"].tolist()}',
                    'priority': 'medium',
                    'details': underprocessing.to_dict()
                }
        
        # Check recent performance trend
        recent = self.results[-30:] if len(self.results) >= 30 else self.results
        recent_wins = sum(1 for r in recent if r.is_correct) / len(recent)
        
        if recent_wins < 0.40:
            return {
                'action': 'RETRAIN_MODEL',
                'reason': f'Recent win rate poor: {recent_wins*100:.1f}%',
                'priority': 'high'
            }
        
        return {
            'action': 'CONTINUE',
            'reason': 'No significant issues detected',
            'priority': 'low'
        }
    
    def get_overall_stats(self) -> Dict:
        """Get overall performance statistics"""
        
        if not self.results:
            return {'status': 'no_data'}
        
        df = self._to_dataframe()
        
        return {
            'total_predictions': len(df),
            'total_wins': df['is_correct'].sum(),
            'total_losses': len(df) - df['is_correct'].sum(),
            'win_rate': df['is_correct'].mean() * 100,
            'total_profit': df['profit'].sum(),
            'roi': (df['profit'].sum() / len(df)) * 100,
            'avg_probability': df['predicted_probability'].mean() * 100,
            'actual_probability': df['actual_probability'].mean() * 100,
            'earliest_result': min(r.timestamp for r in self.results).isoformat(),
            'latest_result': max(r.timestamp for r in self.results).isoformat()
        }
    
    def _to_dataframe(self) -> pd.DataFrame:
        """Convert results to DataFrame"""
        
        if not self.results:
            return pd.DataFrame()
        
        data = [{
            'fixture_id': r.fixture_id,
            'league_code': r.league_code,
            'predicted_probability': r.predicted_probability,
            'actual_probability': r.actual_probability,
            'predicted_value': r.predicted_value,
            'actual_value': r.actual_value,
            'is_correct': r.is_correct,
            'profit': r.profit,
            'odds': r.odds,
            'regime': r.regime,
            'confidence_band': r.confidence_band,
            'model_version': r.model_version,
            'timestamp': r.timestamp
        } for r in self.results]
        
        return pd.DataFrame(data)
    
    def export_for_retraining(self) -> Tuple[np.ndarray, np.ndarray]:
        """Export prediction data for model retraining"""
        
        if len(self.results) < 50:
            return None, None
        
        df = self._to_dataframe()
        
        # Return probabilities and actuals for calibration update
        X = df['predicted_probability'].values
        y = df['actual_value'].values
        
        return X, y
    
    def clear_old_results(self, days_to_keep: int = 90):
        """Clear results older than specified days"""
        
        cutoff = datetime.utcnow() - timedelta(days=days_to_keep)
        self.results = [r for r in self.results if r.timestamp > cutoff]
        
        print(f"Cleared results older than {days_to_keep} days. Remaining: {len(self.results)}")


# Demo function
def demo_feedback_loop():
    """Demonstrate feedback loop functionality"""
    
    print("="*60)
    print("  FEEDBACK LOOP DEMONSTRATION")
    print("="*60)
    
    feedback = FeedbackLoop(min_samples_for_analysis=10)
    
    # Simulate some predictions
    import random
    random.seed(42)
    
    leagues = ['BL1', 'PL']
    regimes = ['regular', 'derby', 'end_of_season']
    bands = ['low', 'medium', 'high', 'very_high']
    
    # Generate 50 random predictions with realistic characteristics
    for i in range(50):
        league = random.choice(leagues)
        regime = random.choice(regimes)
        band = random.choice(bands)
        
        pred_prob = random.uniform(0.5, 0.85)
        actual_prob = random.uniform(0.4, 0.80)  # Sometimes actual differs
        
        predicted = 1 if random.random() < pred_prob else 0
        actual = 1 if random.random() < actual_prob else 0
        
        feedback.record_result(
            fixture_id=i,
            league_code=league,
            predicted_probability=pred_prob,
            actual_probability=actual_prob,
            predicted_value=predicted,
            actual_value=actual,
            odds=1.85,
            model_version="v1",
            regime=regime,
            confidence_band=band
        )
    
    # Get stats
    print("\n[Overall Stats]")
    stats = feedback.get_overall_stats()
    for key, value in stats.items():
        if key not in ['earliest_result', 'latest_result']:
            print(f"  {key}: {value}")
    
    # Confidence band analysis
    print("\n[By Confidence Band]")
    band_analysis = feedback.analyze_by_confidence_band()
    if not band_analysis.empty:
        print(band_analysis.to_string(index=False))
    
    # League analysis
    print("\n[By League]")
    league_analysis = feedback.analyze_by_league()
    if not league_analysis.empty:
        print(league_analysis.to_string(index=False))
    
    # Miss analysis
    print("\n[Miss Analysis]")
    miss_analysis = feedback.analyze_misses()
    print(f"  Total misses: {miss_analysis.get('total_misses', 0)}")
    print(f"  Miss rate: {miss_analysis.get('miss_rate', 0):.1f}%")
    
    # Retrain recommendation
    print("\n[Retrain Recommendation]")
    rec = feedback.get_retrain_recommendation()
    print(f"  Action: {rec['action']}")
    print(f"  Reason: {rec['reason']}")
    print(f"  Priority: {rec['priority']}")


if __name__ == "__main__":
    demo_feedback_loop()
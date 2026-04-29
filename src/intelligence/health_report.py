"""Weekly Model Health Report Generator

Generates comprehensive health reports including:
- ROI by league
- Threshold performance
- Calibration accuracy
- Drawdown analysis
- Recommended parameter changes
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import func

logger = logging.getLogger(__name__)


@dataclass
class HealthReport:
    """Weekly health report data"""
    report_date: datetime
    period_start: datetime
    period_end: datetime
    
    # ROI metrics
    total_roi: float = 0
    total_profit: float = 0
    total_bets: int = 0
    total_wins: int = 0
    
    # By league
    bl1_roi: float = 0
    bl1_bets: int = 0
    bl1_win_rate: float = 0
    
    pl_roi: float = 0
    pl_bets: int = 0
    pl_win_rate: float = 0
    
    # Threshold
    threshold_070_wins: int = 0
    threshold_070_total: int = 0
    threshold_055_wins: int = 0
    threshold_055_total: int = 0
    
    # Calibration
    calibration_ece: float = 0
    calibration_mce: float = 0
    calibration_drift: float = 0
    
    # Drawdown
    peak_bankroll: float = 0
    current_bankroll: float = 0
    max_drawdown: float = 0
    max_drawdown_pct: float = 0
    
    # Recommendation
    recommendation: str = "CONTINUE"
    recommendation_reason: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() 
                if v is not None}


class HealthReportGenerator:
    """Generate weekly model health reports"""
    
    def __init__(self, db_session: Session):
        self.db = db_session
        self.min_samples_for_report = 10
    
    def generate_report(
        self,
        period_days: int = 7,
        reference_date: Optional[datetime] = None
    ) -> HealthReport:
        """
        Generate health report for the specified period.
        
        Args:
            period_days: Number of days to look back
            reference_date: End of period (default: now)
        """
        ref_date = reference_date or datetime.utcnow()
        start_date = ref_date - timedelta(days=period_days)
        
        report = HealthReport(
            report_date=ref_date,
            period_start=start_date,
            period_end=ref_date
        )
        
        # Get settled predictions for period
        settled = self._get_settled_predictions(start_date, ref_date)
        
        if len(settled) < self.min_samples_for_report:
            report.recommendation = "INSUFFICIENT_DATA"
            report.recommendation_reason = f"Only {len(settled)} samples"
            return report
        
        # Calculate overall ROI
        self._calculate_overall_metrics(settled, report)
        
        # Calculate by-league metrics  
        self._calculate_league_metrics(settled, report)
        
        # Calculate threshold metrics
        self._calculate_threshold_metrics(settled, report)
        
        # Calculate calibration
        self._calculate_calibration(settled, report)
        
        # Calculate drawdown
        self._calculate_drawdown(settled, report)
        
        # Generate recommendation
        self._generate_recommendation(settled, report)
        
        return report
    
    def _get_settled_predictions(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict]:
        """Get settled predictions for period"""
        from src.data.database import PredictionRecord
        
        results = self.db.query(PredictionRecord).filter(
            PredictionRecord.settled_at >= start_date,
            PredictionRecord.settled_at <= end_date,
            PredictionRecord.is_accepted == True
        ).all()
        
        return [self._record_to_dict(r) for r in results]
    
    def _record_to_dict(self, record) -> Dict[str, Any]:
        """Convert record to dict"""
        return {
            "id": record.id,
            "fixture_id": record.fixture_id,
            "predicted_probability": record.predicted_probability,
            "actual_outcome": record.actual_outcome,
            "is_correct": record.is_correct,
            "profit": record.profit or 0,
            "stake": record.stake_fraction or 0,
            "clv": record.clv or 0,
            "league_code": getattr(record, "league_code", "UNKNOWN"),
            "settled_at": record.settled_at
        }
    
    def _calculate_overall_metrics(
        self,
        settled: List[Dict],
        report: HealthReport
    ) -> None:
        """Calculate overall ROI metrics"""
        
        report.total_bets = len(settled)
        report.total_wins = sum(1 for s in settled if s.get("is_correct"))
        
        total_profit = sum(s.get("profit", 0) for s in settled)
        total_stake = sum(s.get("stake", 0) for s in settled)
        
        report.total_profit = total_profit
        report.total_roi = (total_profit / total_stake * 100) if total_stake > 0 else 0
    
    def _calculate_league_metrics(
        self,
        settled: List[Dict],
        report: HealthReport
    ) -> None:
        """Calculate metrics by league"""
        
        by_league = {}
        for s in settled:
            league = s.get("league_code", "UNKNOWN")
            if league not in by_league:
                by_league[league] = []
            by_league[league].append(s)
        
        for league, predictions in by_league.items():
            bets = len(predictions)
            wins = sum(1 for p in predictions if p.get("is_correct"))
            profit = sum(p.get("profit", 0) for p in predictions)
            stake = sum(p.get("stake", 0) for p in predictions)
            
            roi = (profit / stake * 100) if stake > 0 else 0
            win_rate = (wins / bets * 100) if bets > 0 else 0
            
            if league == "BL1":
                report.bl1_roi = roi
                report.bl1_bets = bets
                report.bl1_win_rate = win_rate
            elif league == "PL":
                report.pl_roi = roi
                report.pl_bets = bets
                report.pl_win_rate = win_rate
            else:
                report.other_roi = roi
                report.other_bets = bets
    
    def _calculate_threshold_metrics(
        self,
        settled: List[Dict],
        report: HealthReport
    ) -> None:
        """Calculate performance by probability threshold"""
        
        # Threshold 0.70 (high confidence)
        threshold_070 = [s for s in settled if s.get("predicted_probability", 0) >= 0.70]
        report.threshold_070_total = len(threshold_070)
        report.threshold_070_wins = sum(1 for s in threshold_070 if s.get("is_correct"))
        
        # Threshold 0.55 (standard)
        threshold_055 = [s for s in settled if s.get("predicted_probability", 0) >= 0.55]
        report.threshold_055_total = len(threshold_055)
        report.threshold_055_wins = sum(1 for s in threshold_055 if s.get("is_correct"))
    
    def _calculate_calibration(
        self,
        settled: List[Dict],
        report: HealthReport
    ) -> None:
        """Calculate calibration metrics"""
        
        # Group by probability bin
        bins = np.linspace(0, 1, 11)
        errors = []
        
        for i in range(len(bins) - 1):
            in_bin = [s for s in settled 
                     if bins[i] <= s.get("predicted_probability", 0) < bins[i + 1]]
            
            if len(in_bin) >= 3:
                avg_pred = np.mean([s.get("predicted_probability", 0) for s in in_bin])
                actual_rate = np.mean([1 if s.get("is_correct") else 0 for s in in_bin])
                
                errors.append({
                    "bin_start": bins[i],
                    "bin_end": bins[i + 1],
                    "n": len(in_bin),
                    "avg_pred": avg_pred,
                    "actual": actual_rate,
                    "error": abs(actual_rate - avg_pred)
                })
        
        if errors:
            total_weight = sum(e["n"] for e in errors)
            report.calibration_ece = sum(
                e["error"] * e["n"] / total_weight for e in errors
            )
            report.calibration_mce = max(e["error"] for e in errors)
        
        # Calculate drift (actual - predicted)
        predicted = [s.get("predicted_probability", 0) for s in settled]
        actual = [1 if s.get("is_correct") else 0 for s in settled]
        
        if predicted:
            report.calibration_drift = np.mean(actual) - np.mean(predicted)
    
    def _calculate_drawdown(
        self,
        settled: List[Dict],
        report: HealthReport
    ) -> None:
        """Calculate drawdown metrics"""
        
        if not settled:
            return
        
        # Sort by settled date
        sorted_settled = sorted(settled, key=lambda x: x.get("settled_at", datetime.min))
        
        # Simulate bankroll
        bankroll = 10000
        peak = bankroll
        max_dd = 0
        
        for s in settled:
            bankroll += s.get("profit", 0)
            if bankroll > peak:
                peak = bankroll
            dd = peak - bankroll
            if dd > max_dd:
                max_dd = dd
        
        report.peak_bankroll = peak
        report.current_bankroll = bankroll
        report.max_drawdown = max_dd
        report.max_drawdown_pct = (max_dd / peak * 100) if peak > 0 else 0
    
    def _generate_recommendation(
        self,
        settled: List[Dict],
        report: HealthReport
    ) -> None:
        """Generate recommendation based on metrics"""
        
        reasons = []
        
        # Check ROI
        if report.total_roi < -10:
            reasons.append(f"Negative ROI: {report.total_roi:.1f}%")
        elif report.total_roi < 0:
            reasons.append(f"Slight loss: {report.total_roi:.1f}%")
        
        # Check calibration
        if report.calibration_ece > 0.15:
            reasons.append(f"Calibration error: {report.calibration_ece:.2f}")
        
        # Check drawdown
        if report.max_drawdown_pct > 20:
            reasons.append(f"High drawdown: {report.max_drawdown_pct:.1f}%")
        
        # Check threshold performance
        if report.threshold_070_total >= 5:
            if (report.threshold_070_wins / report.threshold_070_total) < 0.50:
                reasons.append("High threshold underperforming")
        
        # Generate final recommendation
        if len(reasons) >= 2:
            report.recommendation = "INVESTIGATE"
            report.recommendation_reason = "; ".join(reasons)
        elif report.total_roi > 10:
            report.recommendation = "CONTINUE"
            report.recommendation_reason = "Strong performance"
        elif report.total_roi > 0:
            report.recommendation = "CONTINUE"
            report.recommendation_reason = "Positive ROI"
        elif report.calibration_drift > 0.1:
            report.recommendation = "RETRAIN_CALIBRATION"
            report.recommendation_reason = f"Under-confident by {report.calibration_drift:.1%}"
        else:
            report.recommendation = "CONTINUE"
            report.recommendation_reason = "No significant issues"
    
    def save_report(
        self,
        report: HealthReport
    ) -> int:
        """Save report to database"""
        from src.data.database import ModelHealthReport
        
        db_report = ModelHealthReport(
            report_date=report.report_date,
            period_start=report.period_start,
            period_end=report.period_end,
            bl1_roi=report.bl1_roi,
            bl1_bets=report.bl1_bets,
            bl1_win_rate=report.bl1_win_rate,
            pl_roi=report.pl_roi,
            pl_bets=report.pl_bets,
            pl_win_rate=report.pl_win_rate,
            other_roi=report.other_roi,
            other_bets=report.other_bets,
            threshold_070_wins=report.threshold_070_wins,
            threshold_070_total=report.threshold_070_total,
            threshold_055_wins=report.threshold_055_wins,
            threshold_055_total=report.threshold_055_total,
            calibration_ece=report.calibration_ece,
            calibration_mce=report.calibration_mce,
            calibration_drift=report.calibration_drift,
            peak_bankroll=report.peak_bankroll,
            current_bankroll=report.current_bankroll,
            max_drawdown=report.max_drawdown,
            max_drawdown_pct=report.max_drawdown_pct,
            recommendation=report.recommendation,
            recommendation_reason=report.recommendation_reason
        )
        
        self.db.add(db_report)
        self.db.commit()
        
        return db_report.id
    
    def get_recent_reports(
        self,
        weeks: int = 4
    ) -> List[Dict]:
        """Get recent health reports"""
        from src.data.database import ModelHealthReport
        
        cutoff = datetime.utcnow() - timedelta(weeks=weeks)
        
        reports = self.db.query(ModelHealthReport).filter(
            ModelHealthReport.report_date >= cutoff
        ).order_by(ModelHealthReport.report_date.desc()).all()
        
        return [r.__dict__ for r in reports]
    
    def get_parameter_recommendations(
        self,
        report: HealthReport
    ) -> Dict[str, Any]:
        """Generate parameter change recommendations"""
        
        recommendations = []
        
        # Check if thresholds should change
        if report.threshold_070_wins / max(1, report.threshold_070_total) < 0.50:
            recommendations.append({
                "parameter": "high_threshold",
                "current": 0.70,
                "recommended": 0.65,
                "reason": "High threshold underperforming"
            })
        
        if report.bl1_roi < 0 and report.bl1_bets > 10:
            recommendations.append({
                "parameter": "BL1_threshold",
                "current": 0.70,
                "recommended": 0.75,
                "reason": "BL1 losing money"
            })
        
        if report.calibration_drift > 0.1:
            recommendations.append({
                "parameter": "calibration",
                "action": "retrain",
                "reason": "Predictions under-confident"
            })
        
        return {
            "recommendations": recommendations,
            "should_change": len(recommendations) > 0
        }


def generate_weekly_report(db_session: Session) -> Dict[str, Any]:
    """Convenience function to generate and save weekly report"""
    
    generator = HealthReportGenerator(db_session)
    report = generator.generate_report(period_days=7)
    
    # Save to database
    report_id = generator.save_report(report)
    
    return {
        "report_id": report_id,
        "report": report.to_dict(),
        "recommendations": generator.get_parameter_recommendations(report)
    }
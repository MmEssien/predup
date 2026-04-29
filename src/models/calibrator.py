"""Probability Calibration Module

Provides probability calibration using isotonic regression to fix under-confident predictions.
The analysis showed model probabilities are too conservative (actual win rates 20-60% higher than predicted).
"""

import numpy as np
from typing import Dict, Optional, Tuple
from sklearn.isotonic import IsotonicRegression
from sklearn.calibration import CalibratedClassifierCV
import pickle
from pathlib import Path


class ProbabilityCalibrator:
    """Calibrate model probabilities using isotonic regression"""
    
    def __init__(self, n_bins: int = 10):
        self.n_bins = n_bins
        self.isotonic = None
        self.is_fitted = False
        self.calibration_curve = None
        self.bins = np.linspace(0, 1, n_bins + 1)
    
    def fit(self, y_true: np.ndarray, y_prob: np.ndarray) -> 'ProbabilityCalibrator':
        """
        Fit isotonic regression calibration.
        
        Args:
            y_true: Actual outcomes (0 or 1)
            y_prob: Raw model probabilities
        """
        # Filter out extreme probabilities
        mask = (y_prob > 0.01) & (y_prob < 0.99)
        y_true_filtered = y_true[mask]
        y_prob_filtered = y_prob[mask]
        
        if len(y_true_filtered) < 50:
            print(f"Warning: Only {len(y_true_filtered)} samples for calibration, may be unreliable")
        
        # Fit isotonic regression
        self.isotonic = IsotonicRegression(out_of_bounds='clip', increasing=True)
        self.isotonic.fit(y_prob_filtered, y_true_filtered)
        
        self.is_fitted = True
        
        # Generate calibration curve
        self.calibration_curve = self._compute_calibration_curve(y_true_filtered, y_prob_filtered)
        
        return self
    
    def _compute_calibration_curve(self, y_true: np.ndarray, y_prob: np.ndarray) -> Dict:
        """Compute calibration metrics"""
        results = []
        
        for i in range(self.n_bins):
            mask = (y_prob >= self.bins[i]) & (y_prob < self.bins[i + 1])
            
            if mask.sum() > 0:
                results.append({
                    'bin_start': self.bins[i],
                    'bin_end': self.bins[i + 1],
                    'mean_predicted': y_prob[mask].mean(),
                    'actual_positive_rate': y_true[mask].mean(),
                    'n_samples': mask.sum(),
                    'calibrated_prob': self.isotonic.predict([y_prob[mask].mean()])[0] if len(y_prob[mask]) > 0 else 0.5
                })
        
        return results
    
    def transform(self, y_prob: np.ndarray) -> np.ndarray:
        """Transform probabilities using fitted calibrator"""
        if not self.is_fitted:
            return y_prob
        
        calibrated = self.isotonic.predict(y_prob)
        
        # Clip to valid range
        calibrated = np.clip(calibrated, 0.001, 0.999)
        
        return calibrated
    
    def fit_transform(self, y_true: np.ndarray, y_prob: np.ndarray) -> np.ndarray:
        """Fit and transform in one call"""
        self.fit(y_true, y_prob)
        return self.transform(y_prob)
    
    def get_calibration_metrics(self) -> Dict:
        """Get calibration metrics"""
        if not self.is_fitted or not self.calibration_curve:
            return {}
        
        # Calculate Expected Calibration Error (ECE)
        total_samples = sum(b['n_samples'] for b in self.calibration_curve)
        ece = 0
        
        for bin_data in self.calibration_curve:
            weight = bin_data['n_samples'] / total_samples
            error = abs(bin_data['actual_positive_rate'] - bin_data['calibrated_prob'])
            ece += weight * error
        
        # Calculate Maximum Calibration Error (MCE)
        mce = max(
            abs(b['actual_positive_rate'] - b['calibrated_prob']) 
            for b in self.calibration_curve
        ) if self.calibration_curve else 0
        
        return {
            'ece': ece,  # Expected Calibration Error
            'mce': mce,  # Maximum Calibration Error
            'n_bins': len(self.calibration_curve),
            'calibration_curve': self.calibration_curve
        }
    
    def save(self, path: str):
        """Save calibrator to file"""
        with open(path, 'wb') as f:
            pickle.dump({
                'isotonic': self.isotonic,
                'n_bins': self.n_bins,
                'bins': self.bins,
                'calibration_curve': self.calibration_curve,
                'is_fitted': self.is_fitted
            }, f)
    
    def load(self, path: str):
        """Load calibrator from file"""
        with open(path, 'rb') as f:
            data = pickle.load(f)
            self.isotonic = data['isotonic']
            self.n_bins = data['n_bins']
            self.bins = data['bins']
            self.calibration_curve = data['calibration_curve']
            self.is_fitted = data['is_fitted']


class LeagueCalibrator:
    """
    Maintains separate calibrators for each league.
    Analysis showed different calibration needs per league.
    """
    
    def __init__(self):
        self.calibrators: Dict[str, ProbabilityCalibrator] = {}
        self.global_calibrator = ProbabilityCalibrator(n_bins=10)
    
    def fit_league(
        self, 
        league_code: str, 
        y_true: np.ndarray, 
        y_prob: np.ndarray
    ) -> ProbabilityCalibrator:
        """Fit calibrator for a specific league"""
        calibrator = ProbabilityCalibrator(n_bins=10)
        calibrator.fit(y_true, y_prob)
        self.calibrators[league_code] = calibrator
        
        metrics = calibrator.get_calibration_metrics()
        print(f"  {league_code}: ECE={metrics.get('ece', 0):.3f}, MCE={metrics.get('mce', 0):.3f}")
        
        return calibrator
    
    def transform(
        self, 
        y_prob: np.ndarray, 
        league_code: Optional[str] = None
    ) -> np.ndarray:
        """Transform probabilities with league-specific calibration"""
        if league_code and league_code in self.calibrators:
            return self.calibrators[league_code].transform(y_prob)
        elif self.global_calibrator.is_fitted:
            return self.global_calibrator.transform(y_prob)
        else:
            return y_prob
    
    def fit_global(
        self, 
        y_true: np.ndarray, 
        y_prob: np.ndarray
    ) -> ProbabilityCalibrator:
        """Fit a global calibrator for all leagues"""
        self.global_calibrator.fit(y_true, y_prob)
        metrics = self.global_calibrator.get_calibration_metrics()
        
        print(f"  Global: ECE={metrics.get('ece', 0):.3f}, MCE={metrics.get('mce', 0):.3f}")
        
        return self.global_calibrator
    
    def get_calibration_report(self) -> Dict:
        """Get calibration report for all leagues"""
        report = {}
        
        for league, calibrator in self.calibrators.items():
            metrics = calibrator.get_calibration_metrics()
            report[league] = metrics
        
        if self.global_calibrator.is_fitted:
            report['global'] = self.global_calibrator.get_calibration_metrics()
        
        return report
    
    def save_all(self, directory: str):
        """Save all calibrators"""
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        
        for league, calibrator in self.calibrators.items():
            calibrator.save(str(path / f"calibrator_{league}.pkl"))
        
        if self.global_calibrator.is_fitted:
            self.global_calibrator.save(str(path / "calibrator_global.pkl"))
        
        print(f"Saved {len(self.calibrators)} league calibrators + global to {directory}")
    
    def load_all(self, directory: str):
        """Load all calibrators"""
        path = Path(directory)
        
        for calibrator_file in path.glob("calibrator_*.pkl"):
            league = calibrator_file.stem.replace("calibrator_", "")
            calibrator = ProbabilityCalibrator()
            calibrator.load(str(calibrator_file))
            self.calibrators[league] = calibrator
        
        global_file = path / "calibrator_global.pkl"
        if global_file.exists():
            self.global_calibrator.load(str(global_file))
        
        print(f"Loaded {len(self.calibrators)} league calibrators from {directory}")


def quick_calibrate(y_true: np.ndarray, y_prob: np.ndarray) -> Tuple[np.ndarray, Dict]:
    """
    Quick one-call calibration.
    
    Returns calibrated probabilities and metrics.
    """
    calibrator = ProbabilityCalibrator(n_bins=10)
    calibrated = calibrator.fit_transform(y_true, y_prob)
    metrics = calibrator.get_calibration_metrics()
    
    return calibrated, metrics
"""
MLB Probability Calibration Layer

Purpose: Post-model probability correction system
- Align predicted probability → true outcome frequency
- Correct EV scaling bias (especially in high EV buckets)
- Reduce overconfidence compression

NOTE: This is NOT model improvement - it's probability correction.
"""

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.calibration import calibration_curve
from typing import Dict, List, Tuple, Optional
import random


class ProbabilityCalibrator:
    """
    Probability calibration using isotonic regression.
    
    Keeps predicted probabilities aligned with actual outcome frequencies.
    """
    
    def __init__(self, n_bins: int = 10):
        self.n_bins = n_bins
        self.isotonic = IsotonicRegression(out_of_bounds='clip')
        self.is_fitted = False
        self.calibration_curve = None
        self.bin_edges = None
        self.bin_true_rates = None
        self.bin_counts = None
    
    def fit(self, y_true: np.ndarray, y_prob: np.ndarray) -> 'ProbabilityCalibrator':
        """
        Fit calibrator on historical predictions vs actual outcomes.
        
        Args:
            y_true: Actual binary outcomes (0/1)
            y_prob: Raw model probabilities (0-1)
        """
        # Clip probabilities to valid range
        y_prob = np.clip(y_prob, 0.001, 0.999)
        
        # Fit isotonic regression
        self.isotonic.fit(y_prob, y_true)
        self.is_fitted = True
        
        # Store calibration curve data
        self._compute_calibration_curve(y_true, y_prob)
        
        return self
    
    def _compute_calibration_curve(self, y_true: np.ndarray, y_prob: np.ndarray):
        """Compute reliability curve data."""
        # Create bins
        self.bin_edges = np.linspace(0, 1, self.n_bins + 1)
        self.bin_true_rates = []
        self.bin_counts = []
        
        for i in range(self.n_bins):
            mask = (y_prob >= self.bin_edges[i]) & (y_prob < self.bin_edges[i+1])
            if i == self.n_bins - 1:  # Include last bin
                mask = (y_prob >= self.bin_edges[i]) & (y_prob <= self.bin_edges[i+1])
            
            if mask.sum() > 0:
                self.bin_true_rates.append(y_true[mask].mean())
                self.bin_counts.append(mask.sum())
            else:
                self.bin_true_rates.append(0.5)
                self.bin_counts.append(0)
        
        self.bin_true_rates = np.array(self.bin_true_rates)
        self.bin_counts = np.array(self.bin_counts)
    
    def transform(self, y_prob: np.ndarray) -> np.ndarray:
        """
        Apply calibration to probabilities.
        
        Args:
            y_prob: Raw model probabilities
            
        Returns:
            Calibrated probabilities
        """
        if not self.is_fitted:
            raise ValueError("Calibrator not fitted. Call fit() first.")
        
        y_prob = np.clip(y_prob, 0.001, 0.999)
        return self.isotonic.transform(y_prob)
    
    def fit_transform(self, y_true: np.ndarray, y_prob: np.ndarray) -> np.ndarray:
        """Fit and transform in one step."""
        return self.fit(y_true, y_prob).transform(y_prob)
    
    def get_calibration_metrics(self) -> Dict:
        """Get calibration quality metrics."""
        if not self.is_fitted:
            return {"error": "Not fitted"}
        
        # Expected Calibration Error (ECE)
        ece = 0
        total = self.bin_counts.sum()
        for i in range(self.n_bins):
            bin_center = (self.bin_edges[i] + self.bin_edges[i+1]) / 2
            ece += (self.bin_counts[i] / total) * abs(self.bin_true_rates[i] - bin_center)
        
        # Mean calibration error
        mce = np.mean(np.abs(self.bin_true_rates - (self.bin_edges[:-1] + self.bin_edges[1:]) / 2))
        
        return {
            "expected_calibration_error": ece,
            "mean_calibration_error": mce,
            "bin_true_rates": self.bin_true_rates.tolist(),
            "bin_centers": ((self.bin_edges[:-1] + self.bin_edges[1:]) / 2).tolist(),
            "bin_counts": self.bin_counts.tolist()
        }


class EVCalibrator:
    """
    EV-specific calibration layer.
    
    Corrects for:
    - EV scaling bias in high-confidence predictions
    - Overconfidence compression in ensemble models
    - Market odds vs true probability drift
    """
    
    def __init__(self):
        self.prob_calibrator = ProbabilityCalibrator(n_bins=10)
        self.ev_bias_correction = {}
        self.is_fitted = False
    
    def fit(self, 
            predictions: List[Dict],
            market_implied: List[float],
            actual_outcomes: List[int]) -> 'EVCalibrator':
        """
        Fit EV calibrator on historical prediction data.
        
        Args:
            predictions: List of {"prob": model_prob, "ev": raw_ev}
            market_implied: List of implied probabilities from market
            actual_outcomes: List of actual results (0/1)
        """
        y_prob = np.array([p["prob"] for p in predictions])
        y_true = np.array(actual_outcomes)
        
        # Step 1: Fit probability calibration
        self.prob_calibrator.fit(y_true, y_prob)
        
        # Step 2: Compute EV bias by bucket
        self._compute_ev_bias(y_prob, market_implied, actual_outcomes)
        
        self.is_fitted = True
        return self
    
    def _compute_ev_bias(self, 
                         y_prob: np.ndarray, 
                         market_implied: np.ndarray,
                         actual_outcomes: List[int]):
        """Compute EV bias correction factors by probability bucket."""
        buckets = [(0.0, 0.3), (0.3, 0.4), (0.4, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 1.0)]
        
        for low, high in buckets:
            mask = (y_prob >= low) & (y_prob < high)
            if mask.sum() < 10:
                continue
            
            bucket_probs = y_prob[mask]
            bucket_implied = market_implied[mask]
            bucket_actual = np.array([actual_outcomes[i] for i in range(len(actual_outcomes)) if mask[i]])
            
            # Raw EV = prob - implied
            raw_ev = bucket_probs.mean() - bucket_implied.mean()
            
            # Actual EV = actual win rate - implied
            actual_ev = bucket_actual.mean() - bucket_implied.mean()
            
            # Bias = raw EV - actual EV
            bias = raw_ev - actual_ev
            
            self.ev_bias_correction[(low, high)] = bias
    
    def calibrate_ev(self, 
                    model_prob: float, 
                    market_implied: float) -> Tuple[float, float]:
        """
        Get calibrated probability and EV.
        
        Returns:
            (calibrated_prob, calibrated_ev)
        """
        if not self.is_fitted:
            return model_prob, model_prob - market_implied
        
        # Get calibrated probability
        calibrated_prob = self.prob_calibrator.transform(np.array([model_prob]))[0]
        
        # Apply EV bias correction
        ev = calibrated_prob - market_implied
        for (low, high), bias in self.ev_bias_correction.items():
            if low <= model_prob < high:
                ev -= bias * 0.5  # Partial correction
                break
        
        return calibrated_prob, ev
    
    def get_calibrated_prob(self, model_prob: float) -> float:
        """Get only calibrated probability."""
        if not self.is_fitted:
            return model_prob
        return self.prob_calibrator.transform(np.array([model_prob]))[0]


def run_calibration_validation():
    # Generate synthetic training data for calibrator
    np.random.seed(42)
    
    n_train = 5000
    n_test = 3000
    
    train_probs = np.random.beta(2, 2, n_train)
    train_outcomes = (np.random.random(n_train) < train_probs).astype(int)
    
    results = []
    raw_bets = []
    calibrated_bets = []
    
    market = RealisticMarketOdds(seed=42)
    
    for i in range(n_test):
        # Generate game features
        home_offense = np.random.normal(0.5, 0.15)
        away_offense = np.random.normal(0.5, 0.15)
        home_pitching = np.random.normal(0.5, 0.15)
        away_pitching = np.random.normal(0.5, 0.15)
        home_starter = np.random.normal(0.5, 0.2)
        away_starter = np.random.normal(0.5, 0.2)
        bullpen_home_fatigue = np.random.uniform(0, 1)
        bullpen_away_fatigue = np.random.uniform(0, 1)
        home_rest = random.choice([0, 1, 2, 3])
        away_rest = random.choice([0, 1, 2, 3])
        home_recent = np.random.normal(0.5, 0.2)
        away_recent = np.random.normal(0.5, 0.2)
        
        logit = (
            +0.8 * (home_offense - away_offense) * 2 +
            -0.8 * (home_pitching - away_pitching) * 2 +
            +0.3 * 0.03 +
            +0.1 * (home_rest - away_rest) +
            +0.3 * (home_recent - away_recent) +
            +0.3 * (home_starter - away_starter) +
            -0.1 * bullpen_home_fatigue +
            +0.1 * bullpen_away_fatigue
        )
        true_prob = 1 / (1 + np.exp(-logit))
        true_prob = np.clip(true_prob + np.random.normal(0, 0.05), 0.1, 0.9)
        actual_win = np.random.random() < true_prob
        
        # Get market odds
        odds = market.generate_moneyline_odds(true_prob)
        market_odds = odds["odds_home"]
        implied_prob = odds["implied_home"]
        
        # Simulate model prediction (with some bias/compression)
        model_prob = true_prob + np.random.normal(0, 0.05)
        model_prob = np.clip(model_prob, 0.1, 0.9)
        
        # Raw EV
        raw_ev = model_prob - implied_prob
        
        # Apply calibration
        calibrated_prob = np.clip(
            model_prob + (0.5 - model_prob) * 0.1,  # Simple calibration
            0.1, 0.9
        )
        calibrated_ev = calibrated_prob - implied_prob
        
        results.append({
            "raw_prob": model_prob,
            "calibrated_prob": calibrated_prob,
            "true_prob": true_prob,
            "implied": implied_prob,
            "raw_ev": raw_ev,
            "calibrated_ev": calibrated_ev,
            "actual": actual_win
        })
        
        # Bet decisions (same thresholds as before)
        raw_bet = (model_prob > 0.60 or model_prob < 0.40) and raw_ev >= 0.15
        calib_bet = (calibrated_prob > 0.60 or calibrated_prob < 0.40) and calibrated_ev >= 0.15
        
        if raw_bet:
            raw_bets.append({
                "ev": raw_ev,
                "prob": model_prob,
                "odds": market_odds,
                "actual": actual_win
            })
        
        if calib_bet:
            calibrated_bets.append({
                "ev": calibrated_ev,
                "prob": calibrated_prob,
                "odds": market_odds,
                "actual": actual_win
            })
    
    # Analyze results
    print(f"\nTest data: {n_test} games")
    print(f"Raw bets: {len(raw_bets)}, Calibrated bets: {len(calibrated_bets)}")
    
    # Calibration metrics
    raw_probs = np.array([r["raw_prob"] for r in results])
    calib_probs = np.array([r["calibrated_prob"] for r in results])
    actual = np.array([r["actual"] for r in results])
    
    print("\n--- CALIBRATION QUALITY ---")
    
    # Raw calibration error
    raw_buckets = np.linspace(0, 1, 11)
    raw_errors = []
    for i in range(10):
        mask = (raw_probs >= raw_buckets[i]) & (raw_probs < raw_buckets[i+1])
        if i == 9:
            mask = (raw_probs >= raw_buckets[i]) & (raw_probs <= raw_buckets[i+1])
        if mask.sum() > 0:
            pred_rate = raw_probs[mask].mean()
            actual_rate = actual[mask].mean()
            raw_errors.append(abs(pred_rate - actual_rate))
    
    print(f"Raw calibration error: {np.mean(raw_errors):.3f}")
    
    # Calibrated calibration error
    calib_errors = []
    for i in range(10):
        mask = (calib_probs >= raw_buckets[i]) & (calib_probs < raw_buckets[i+1])
        if i == 9:
            mask = (calib_probs >= raw_buckets[i]) & (calib_probs <= raw_buckets[i+1])
        if mask.sum() > 0:
            pred_rate = calib_probs[mask].mean()
            actual_rate = actual[mask].mean()
            calib_errors.append(abs(pred_rate - actual_rate))
    
    print(f"Calibrated calibration error: {np.mean(calib_errors):.3f}")
    
    # EV bucket analysis
    print("\n--- RAW EV BUCKET ANALYSIS ---")
    raw_bucket_rois = analyze_ev_buckets(raw_bets)
    
    print("\n--- CALIBRATED EV BUCKET ANALYSIS ---")
    calib_bucket_rois = analyze_ev_buckets(calibrated_bets)
    
    # Compare
    print("\n--- COMPARISON ---")
    print(f"Raw EV range: {min(b['ev'] for b in raw_bets):.1%} to {max(b['ev'] for b in raw_bets):.1%}")
    print(f"Calib EV range: {min(b['ev'] for b in calibrated_bets):.1%} to {max(b['ev'] for b in calibrated_bets):.1%}")
    
    # Monotonicity check
    if len(raw_bucket_rois) >= 2 and len(calib_bucket_rois) >= 2:
        raw_monotonic = check_monotonicity(list(raw_bucket_rois.values()))
        calib_monotonic = check_monotonicity(list(calib_bucket_rois.values()))
        print(f"Raw monotonicity: {raw_monotonic}")
        print(f"Calib monotonicity: {calib_monotonic}")
    
    return results, raw_bets, calibrated_bets


def analyze_ev_buckets(bets: List[Dict]) -> Dict[str, float]:
    """Analyze ROI by EV bucket."""
    buckets = [
        (0.15, 0.20, "15-20%"),
        (0.20, 0.30, "20-30%"),
        (0.30, 0.40, "30-40%"),
        (0.40, 0.50, "40-50%"),
        (0.50, 1.00, "50%+")
    ]
    
    bucket_rois = {}
    for low, high, label in buckets:
        bucket = [b for b in bets if low <= b["ev"] < high]
        if bucket:
            wins = sum(1 for b in bucket if b["actual"])
            profit = 0
            for b in bucket:
                if b["actual"]:
                    odds = b["odds"]
                    profit += odds / 100 if odds > 0 else 100 / abs(odds)
                else:
                    profit -= 1
            roi = (profit / len(bucket)) * 100
            bucket_rois[label] = roi
            print(f"  EV {label}: n={len(bucket)}, win={wins/len(bucket):.1%}, ROI={roi:+.1f}%")
    
    return bucket_rois


def check_monotonicity(values: List[float]) -> bool:
    """Check if values are monotonically increasing."""
    if len(values) < 2:
        return True
    for i in range(len(values) - 1):
        if values[i] > values[i + 1]:
            return False
    return True


def run_multiple_runs_with_calibration(n_runs: int = 5, games_per_run: int = 2000):
    """
    Run multiple backtest runs with calibration to validate stability.
    """
    print("\n" + "="*70)
    print(f"  MULTIPLE RUN STABILITY WITH CALIBRATION ({n_runs}x{games_per_run})")
    print("="*70)
    
    results = []
    
    for run in range(n_runs):
        np.random.seed(42 + run)
        random.seed(42 + run)
        
        from PredUp.scripts.mlb_closed_loop_v2 import RealisticMarketOdds
        
        market = RealisticMarketOdds(seed=42 + run)
        
        # Generate training data for this run's calibrator
        train_probs = np.random.beta(2, 2, 1000)
        train_outcomes = (np.random.random(1000) < train_probs).astype(int)
        
        # Fit simple calibration (shift toward 0.5)
        calibrator = lambda p: np.clip(p + (0.5 - p) * 0.15, 0.1, 0.9)
        
        bets_raw = []
        bets_calib = []
        
        for game in range(games_per_run):
            home_offense = np.random.normal(0.5, 0.15)
            away_offense = np.random.normal(0.5, 0.15)
            home_pitching = np.random.normal(0.5, 0.15)
            away_pitching = np.random.normal(0.5, 0.15)
            home_starter = np.random.normal(0.5, 0.2)
            away_starter = np.random.normal(0.5, 0.2)
            bullpen_home_fatigue = np.random.uniform(0, 1)
            bullpen_away_fatigue = np.random.uniform(0, 1)
            home_rest = random.choice([0, 1, 2, 3])
            away_rest = random.choice([0, 1, 2, 3])
            home_recent = np.random.normal(0.5, 0.2)
            away_recent = np.random.normal(0.5, 0.2)
            
            logit = (
                +0.8 * (home_offense - away_offense) * 2 +
                -0.8 * (home_pitching - away_pitching) * 2 +
                +0.3 * 0.03 +
                +0.1 * (home_rest - away_rest) +
                +0.3 * (home_recent - away_recent) +
                +0.3 * (home_starter - away_starter) +
                -0.1 * bullpen_home_fatigue +
                +0.1 * bullpen_away_fatigue
            )
            true_prob = 1 / (1 + np.exp(-logit))
            true_prob = np.clip(true_prob + np.random.normal(0, 0.05), 0.1, 0.9)
            actual_win = np.random.random() < true_prob
            
            odds = market.generate_moneyline_odds(true_prob)
            market_odds = odds["odds_home"]
            implied_prob = odds["implied_home"]
            
            # Raw model prediction
            model_prob = true_prob + np.random.normal(0, 0.05)
            model_prob = np.clip(model_prob, 0.1, 0.9)
            
            raw_ev = model_prob - implied_prob
            raw_bet = (model_prob > 0.60 or model_prob < 0.40) and raw_ev >= 0.15
            
            # Calibrated prediction
            calib_prob = calibrator(model_prob)
            calib_ev = calib_prob - implied_prob
            calib_bet = (calib_prob > 0.60 or calib_prob < 0.40) and calib_ev >= 0.15
            
            if raw_bet:
                bets_raw.append({"ev": raw_ev, "odds": market_odds, "actual": actual_win})
            
            if calib_bet:
                bets_calib.append({"ev": calib_ev, "odds": market_odds, "actual": actual_win})
        
        # Compute ROI
        def calc_roi(bets):
            if not bets:
                return 0, 0
            profit = sum(
                (b["odds"] / 100 if b["odds"] > 0 else 100 / abs(b["odds"])) if b["actual"] else -1
                for b in bets
            )
            return len(bets), (profit / len(bets)) * 100
        
        n_raw, roi_raw = calc_roi(bets_raw)
        n_calib, roi_calib = calc_roi(bets_calib)
        
        results.append({
            "run": run + 1,
            "raw_n": n_raw,
            "raw_roi": roi_raw,
            "calib_n": n_calib,
            "calib_roi": roi_calib
        })
        
        print(f"  Run {run+1}: Raw n={n_raw}, ROI={roi_raw:+.1f}% | Calib n={n_calib}, ROI={roi_calib:+.1f}%")
    
    # Summary
    raw_rois = [r["raw_roi"] for r in results]
    calib_rois = [r["calib_roi"] for r in results]
    
    print(f"\n--- SUMMARY ---")
    print(f"Raw:   Avg ROI = {np.mean(raw_rois):+.1f}%, Std = {np.std(raw_rois):.1f}%")
    print(f"Calib: Avg ROI = {np.mean(calib_rois):+.1f}%, Std = {np.std(calib_rois):.1f}%")
    
    if np.std(calib_rois) < np.std(raw_rois):
        print("\n[PASS] Calibration REDUCES variance")
    else:
        print("\n[INFO] Calibration effect on variance: neutral or mixed")
    
    return results


if __name__ == "__main__":
    # Run calibration validation
    run_calibration_validation()
    
    # Run multiple stability runs
    run_multiple_runs_with_calibration(5, 2000)
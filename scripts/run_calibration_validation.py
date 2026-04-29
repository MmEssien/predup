"""
Standalone Calibration Validation
Run separately from main pipeline to avoid import conflicts
"""

import numpy as np
import random
from sklearn.isotonic import IsotonicRegression
from typing import Dict, List, Tuple
import sys
from pathlib import Path


class RealisticMarketOdds:
    def __init__(self, seed=None):
        self.rng = np.random.default_rng(seed)
        self.overround_range = (0.04, 0.10)
        self.favorite_bias = 0.07
        self.noise_probability = 0.10
        self.noise_range = (-0.08, 0.08)
    
    def generate_moneyline_odds(self, true_prob_home: float) -> dict:
        prob_home = true_prob_home
        prob_away = 1 - true_prob_home
        
        if prob_home > 0.5:
            bias = self.favorite_bias * (prob_home - 0.5) * 2
            prob_home = prob_home - bias
            prob_away = 1 - prob_home
        else:
            bias = self.favorite_bias * (prob_away - 0.5) * 2
            prob_away = prob_away - bias
            prob_home = 1 - prob_away
        
        overround = self.rng.uniform(*self.overround_range)
        total = prob_home + prob_away
        adjusted_total = total * (1 + overround)
        
        prob_home_adj = (prob_home / total) * adjusted_total
        prob_away_adj = (prob_away / total) * adjusted_total
        
        has_noise = False
        if self.rng.random() < self.noise_probability:
            noise = self.rng.uniform(*self.noise_range)
            prob_home_adj = np.clip(prob_home_adj + noise, 0.05, 0.95)
            prob_away_adj = 1 - prob_home_adj
            has_noise = True
        
        if prob_home_adj >= 0.5:
            odds_home = int(-(prob_home_adj / (1 - prob_home_adj)) * 100)
        else:
            odds_home = int(((1 - prob_home_adj) / prob_home_adj) * 100)
        
        return {
            "odds_home": odds_home,
            "implied_home": prob_home_adj,
            "overround_pct": overround * 100,
            "has_noise": has_noise
        }


class ProbabilityCalibrator:
    def __init__(self, n_bins: int = 10):
        self.n_bins = n_bins
        self.isotonic = IsotonicRegression(out_of_bounds='clip')
        self.is_fitted = False
    
    def fit(self, y_true: np.ndarray, y_prob: np.ndarray):
        y_prob = np.clip(y_prob, 0.001, 0.999)
        self.isotonic.fit(y_prob, y_true)
        self.is_fitted = True
        return self
    
    def transform(self, y_prob: np.ndarray) -> np.ndarray:
        if not self.is_fitted:
            raise ValueError("Not fitted")
        y_prob = np.clip(y_prob, 0.001, 0.999)
        return self.isotonic.transform(y_prob)
    
    def fit_transform(self, y_true: np.ndarray, y_prob: np.ndarray) -> np.ndarray:
        return self.fit(y_true, y_prob).transform(y_prob)


def run_calibration_validation():
    print("="*70)
    print("  PROBABILITY CALIBRATION VALIDATION")
    print("="*70)
    
    np.random.seed(42)
    random.seed(42)
    
    # Generate test data
    n_train = 2000
    n_test = 3000
    
    # Training data for calibrator
    train_probs = np.random.beta(2, 2, n_train)
    train_outcomes = (np.random.random(n_train) < train_probs).astype(int)
    
    # Test data
    market = RealisticMarketOdds(seed=42)
    
    test_results = []
    
    for i in range(n_test):
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
        actual_win = int(np.random.random() < true_prob)
        
        odds = market.generate_moneyline_odds(true_prob)
        implied_prob = odds["implied_home"]
        
        # Raw model (simulate with some bias)
        raw_prob = true_prob + np.random.normal(0, 0.08)
        raw_prob = np.clip(raw_prob, 0.1, 0.9)
        
        test_results.append({
            "raw_prob": raw_prob,
            "true_prob": true_prob,
            "implied": implied_prob,
            "actual": actual_win
        })
    
    # Fit calibrator on training data
    calibrator = ProbabilityCalibrator(n_bins=10)
    calibrator.fit(train_outcomes, train_probs)
    
    # Analyze calibration quality
    raw_probs = np.array([r["raw_prob"] for r in test_results])
    actual = np.array([r["actual"] for r in test_results])
    
    # Calibrate test data
    calibrated_probs = calibrator.transform(raw_probs)
    
    # Calibration error by bucket
    print("\n--- CALIBRATION QUALITY ---")
    buckets = np.linspace(0, 1, 11)
    
    raw_errors = []
    calib_errors = []
    
    for i in range(10):
        mask = (raw_probs >= buckets[i]) & (raw_probs < buckets[i+1])
        if i == 9:
            mask = (raw_probs >= buckets[i]) & (raw_probs <= buckets[i+1])
        
        if mask.sum() > 0:
            raw_pred = raw_probs[mask].mean()
            raw_actual = actual[mask].mean()
            raw_errors.append(abs(raw_pred - raw_actual))
            
            calib_pred = calibrated_probs[mask].mean()
            calib_actual = actual[mask].mean()
            calib_errors.append(abs(calib_pred - calib_actual))
    
    print(f"Raw calibration error: {np.mean(raw_errors):.3f}")
    print(f"Calibrated calibration error: {np.mean(calib_errors):.3f}")
    
    if np.mean(calib_errors) < np.mean(raw_errors):
        print("[PASS] Calibration improves reliability curve")
    else:
        print("[INFO] Calibration effect neutral on reliability")
    
    # EV bucket analysis - RAW vs CALIBRATED
    print("\n--- EV BUCKET ANALYSIS (RAW vs CALIBRATED) ---")
    
    raw_bets = []
    calib_bets = []
    
    for r, cp in zip(test_results, calibrated_probs):
        raw_ev = r["raw_prob"] - r["implied"]
        calib_ev = cp - r["implied"]
        
        raw_bet = (r["raw_prob"] > 0.60 or r["raw_prob"] < 0.40) and raw_ev >= 0.15
        calib_bet = (cp > 0.60 or cp < 0.40) and calib_ev >= 0.15
        
        market_odds = market.generate_moneyline_odds(r["true_prob"])["odds_home"]
        
        if raw_bet:
            raw_bets.append({"ev": raw_ev, "odds": market_odds, "actual": r["actual"]})
        if calib_bet:
            calib_bets.append({"ev": calib_ev, "odds": market_odds, "actual": r["actual"]})
    
    print(f"\nRaw bets: {len(raw_bets)}, Calibrated bets: {len(calib_bets)}")
    
    def analyze_buckets(bets, label):
        buckets_def = [(0.15, 0.20, "15-20"), (0.20, 0.30, "20-30"), 
                       (0.30, 0.40, "30-40"), (0.40, 0.50, "40-50"), (0.50, 1.0, "50+")]
        
        rois = {}
        for low, high, lbl in buckets_def:
            bucket = [b for b in bets if low <= b["ev"] < high]
            if bucket:
                profit = 0
                for b in bucket:
                    odds = b["odds"] if b["odds"] != 0 else -101  # Default to near-break even
                    if b["actual"]:
                        profit += odds / 100 if odds > 0 else 100 / abs(odds)
                    else:
                        profit -= 1
                roi = (profit / len(bucket)) * 100
                rois[lbl] = roi
                print(f"  {label} EV {lbl}%: n={len(bucket)}, ROI={roi:+.1f}%")
        return rois
    
    raw_rois = analyze_buckets(raw_bets, "Raw")
    calib_rois = analyze_buckets(calib_bets, "Calib")
    
    # Monotonicity check
    def check_monotonic(d):
        vals = list(d.values())
        if len(vals) < 2:
            return True
        for i in range(len(vals) - 1):
            if vals[i] > vals[i+1]:
                return False
        return True
    
    print(f"\nMonotonicity: Raw={check_monotonic(raw_rois)}, Calib={check_monotonic(calib_rois)}")
    
    return raw_rois, calib_rois


def run_stability_test(n_runs=5, games=2000):
    print("\n" + "="*70)
    print(f"  MULTIPLE RUN STABILITY ({n_runs}x{games})")
    print("="*70)
    
    results = []
    
    for run in range(n_runs):
        np.random.seed(42 + run)
        random.seed(42 + run)
        
        market = RealisticMarketOdds(seed=42 + run)
        
        # Simple calibration: shrink toward 0.5
        calibrator = lambda p: np.clip(p + (0.5 - p) * 0.15, 0.1, 0.9)
        
        raw_bets = []
        calib_bets = []
        
        for i in range(games):
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
            actual = int(np.random.random() < true_prob)
            
            odds = market.generate_moneyline_odds(true_prob)
            implied = odds["implied_home"]
            
            raw_prob = true_prob + np.random.normal(0, 0.05)
            raw_prob = np.clip(raw_prob, 0.1, 0.9)
            
            raw_ev = raw_prob - implied
            raw_bet = (raw_prob > 0.60 or raw_prob < 0.40) and raw_ev >= 0.15
            
            calib_prob = calibrator(raw_prob)
            calib_ev = calib_prob - implied
            calib_bet = (calib_prob > 0.60 or calib_prob < 0.40) and calib_ev >= 0.15
            
            if raw_bet:
                raw_bets.append({"odds": odds["odds_home"], "actual": actual})
            if calib_bet:
                calib_bets.append({"odds": odds["odds_home"], "actual": actual})
        
        def calc_roi(bets):
            if not bets:
                return 0
            profit = sum(
                (b["odds"] / 100 if b["odds"] > 0 else 100 / abs(b["odds"])) if b["actual"] else -1
                for b in bets
            )
            return (profit / len(bets)) * 100
        
        raw_roi = calc_roi(raw_bets)
        calib_roi = calc_roi(calib_bets)
        
        results.append({
            "run": run + 1,
            "raw_n": len(raw_bets),
            "raw_roi": raw_roi,
            "calib_n": len(calib_bets),
            "calib_roi": calib_roi
        })
        
        print(f"  Run {run+1}: Raw n={len(raw_bets)}, ROI={raw_roi:+.1f}% | Calib n={len(calib_bets)}, ROI={calib_roi:+.1f}%")
    
    raw_rois = [r["raw_roi"] for r in results]
    calib_rois = [r["calib_roi"] for r in results]
    
    print(f"\n--- SUMMARY ---")
    print(f"Raw:   Avg ROI = {np.mean(raw_rois):+.1f}%, Std = {np.std(raw_rois):.1f}%")
    print(f"Calib: Avg ROI = {np.mean(calib_rois):+.1f}%, Std = {np.std(calib_rois):.1f}%")
    
    if np.std(calib_rois) < np.std(raw_rois):
        print("\n[PASS] Calibration REDUCES variance")
    else:
        print("\n[WARN] Calibration variance effect: mixed")
    
    return results


if __name__ == "__main__":
    run_calibration_validation()
    run_stability_test(5, 2000)
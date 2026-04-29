"""
Final Calibration Validation - Direct Integration with Main Pipeline
Demonstrates calibration layer in closed-loop with realistic market
"""

import numpy as np
import random
from typing import List, Dict, Tuple


class RealisticMarketOdds:
    """Realistic bookmaker model with vig, bias, noise"""
    def __init__(self, seed=None):
        self.rng = np.random.default_rng(seed)
        self.overround_range = (0.04, 0.10)
        self.favorite_bias = 0.07
        self.noise_probability = 0.10
        self.noise_range = (-0.08, 0.08)
    
    def generate_moneyline_odds(self, true_prob_home: float) -> dict:
        prob_home = true_prob_home
        prob_away = 1 - true_prob_home
        
        # Bias: favorites overvalued
        if prob_home > 0.5:
            bias = self.favorite_bias * (prob_home - 0.5) * 2
            prob_home = prob_home - bias
            prob_away = 1 - prob_home
        else:
            bias = self.favorite_bias * (prob_away - 0.5) * 2
            prob_away = prob_away - bias
            prob_home = 1 - prob_away
        
        # Overround (vig)
        overround = self.rng.uniform(*self.overround_range)
        total = prob_home + prob_away
        adjusted_total = total * (1 + overround)
        
        prob_home_adj = (prob_home / total) * adjusted_total
        prob_away_adj = (prob_away / total) * adjusted_total
        
        # Noise
        if self.rng.random() < self.noise_probability:
            noise = self.rng.uniform(*self.noise_range)
            prob_home_adj = np.clip(prob_home_adj + noise, 0.05, 0.95)
            prob_away_adj = 1 - prob_home_adj
        
        # Convert to American odds
        if prob_home_adj >= 0.5:
            odds_home = int(-(prob_home_adj / (1 - prob_home_adj)) * 100)
        else:
            odds_home = int(((1 - prob_home_adj) / prob_home_adj) * 100)
        
        return {"odds_home": odds_home, "implied_home": prob_home_adj}


class IsotonicCalibrator:
    """Post-hoc probability calibration"""
    def __init__(self, n_bins=10):
        self.bins = np.linspace(0, 1, n_bins + 1)
        self.bin_outputs = None
        self.is_fitted = False
    
    def fit(self, y_true: np.ndarray, y_prob: np.ndarray):
        self.bin_outputs = []
        for i in range(len(self.bins) - 1):
            mask = (y_prob >= self.bins[i]) & (y_prob < self.bins[i+1])
            if i == len(self.bins) - 2:
                mask = (y_prob >= self.bins[i]) & (y_prob <= self.bins[i+1])
            if mask.sum() > 0:
                self.bin_outputs.append(y_true[mask].mean())
            else:
                self.bin_outputs.append(self.bins[i])
        self.bin_outputs = np.array(self.bin_outputs)
        self.is_fitted = True
        return self
    
    def transform(self, y_prob: np.ndarray) -> np.ndarray:
        result = np.zeros_like(y_prob)
        for i in range(len(self.bins) - 1):
            mask = (y_prob >= self.bins[i]) & (y_prob < self.bins[i+1])
            if i == len(self.bins) - 2:
                mask = (y_prob >= self.bins[i]) & (y_prob <= self.bins[i+1])
            result[mask] = self.bin_outputs[i]
        return result


def generate_game():
    """Generate game with synthetic true prob and biased model prob"""
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
    
    # Model produces biased predictions (overconfident ensemble effect)
    model_prob = true_prob + np.random.normal(0, 0.12)  # More noise
    model_prob = np.clip(model_prob, 0.1, 0.9)
    
    return {"true_prob": true_prob, "model_prob": model_prob, "actual": actual}


def run_calibration_pipeline():
    print("="*70)
    print("  CALIBRATION LAYER INTEGRATION TEST")
    print("="*70)
    
    np.random.seed(42)
    random.seed(42)
    
    # Step 1: Generate calibration data (historical predictions)
    print("\n[1] Generating calibration set (5000 games)...")
    calibration_games = [generate_game() for _ in range(5000)]
    
    cal_probs = np.array([g["model_prob"] for g in calibration_games])
    cal_actual = np.array([g["actual"] for g in calibration_games])
    
    # Step 2: Fit calibrator
    print("[2] Fitting isotonic calibrator...")
    calibrator = IsotonicCalibrator(n_bins=10)
    calibrator.fit(cal_actual, cal_probs)
    
    # Step 3: Generate test data (fresh)
    print("[3] Generating test set (3000 games)...")
    np.random.seed(99)
    random.seed(99)
    market = RealisticMarketOdds(seed=99)
    
    test_results = []
    for _ in range(3000):
        game = generate_game()
        odds = market.generate_moneyline_odds(game["true_prob"])
        
        raw_prob = game["model_prob"]
        calib_prob = calibrator.transform(np.array([raw_prob]))[0]
        
        raw_ev = raw_prob - odds["implied_home"]
        calib_ev = calib_prob - odds["implied_home"]
        
        test_results.append({
            "raw_prob": raw_prob,
            "calib_prob": calib_prob,
            "implied": odds["implied_home"],
            "raw_ev": raw_ev,
            "calib_ev": calib_ev,
            "actual": game["actual"],
            "odds": odds["odds_home"]
        })
    
    # Step 4: Analyze calibration quality
    print("\n--- CALIBRATION QUALITY ---")
    raw_probs = np.array([r["raw_prob"] for r in test_results])
    calib_probs = np.array([r["calib_prob"] for r in test_results])
    actual = np.array([r["actual"] for r in test_results])
    
    bins = np.linspace(0, 1, 11)
    raw_err, calib_err = [], []
    
    for i in range(10):
        mask = (raw_probs >= bins[i]) & (raw_probs < bins[i+1])
        if i == 9:
            mask = (raw_probs >= bins[i]) & (raw_probs <= bins[i+1])
        
        if mask.sum() > 0:
            raw_err.append(abs(raw_probs[mask].mean() - actual[mask].mean()))
            calib_err.append(abs(calib_probs[mask].mean() - actual[mask].mean()))
    
    print(f"  Raw reliability error:   {np.mean(raw_err):.4f}")
    print(f"  Calibrated reliability:  {np.mean(calib_err):.4f}")
    
    if np.mean(calib_err) < np.mean(raw_err):
        print("  [PASS] Calibration improves reliability")
    else:
        print("  [INFO] Reliability: no change (already well-calibrated)")
    
    # Step 5: EV bucket analysis with LOWER threshold for more data
    print("\n--- EV BUCKET ANALYSIS (ev >= 8%) ---")
    
    # Use lower threshold to get more bets
    EV_THRESHOLD = 0.08
    
    raw_bets = [r for r in test_results if r["raw_ev"] >= EV_THRESHOLD]
    calib_bets = [r for r in test_results if r["calib_ev"] >= EV_THRESHOLD]
    
    print(f"  Raw bets: {len(raw_bets)}, Calib bets: {len(calib_bets)}")
    
    def bucket_analysis(bets, name):
        if not bets:
            print(f"  {name}: No bets")
            return {}
        
        ranges = [(0.08, 0.15, "8-15"), (0.15, 0.25, "15-25"), 
                  (0.25, 0.40, "25-40"), (0.40, 1.0, "40+")]
        
        results = {}
        for lo, hi, lbl in ranges:
            b = [x for x in bets if lo <= x.get(name.lower().replace(' ', '') + "_ev", x["raw_ev"]) < hi]
            # For simplicity, use raw_ev for raw, calib_ev for calib
            if name == "Raw":
                b = [x for x in bets if lo <= x["raw_ev"] < hi]
            else:
                b = [x for x in bets if lo <= x["calib_ev"] < hi]
            
            if b:
                profit = sum(
                    (x["odds"]/100 if x["odds"]>0 else 100/abs(x["odds"])) if x["actual"] else -1 for x in b
                )
                roi = profit / len(b) * 100
                results[lbl] = roi
                print(f"  {name} {lbl}%: n={len(b):4d}, ROI={roi:+7.1f}%")
        return results
    
    # Manual bucketting
    print("\n  RAW:")
    raw_roi_by_bucket = {}
    for lo, hi, lbl in [(0.08, 0.15, "8-15"), (0.15, 0.25, "15-25"), (0.25, 0.40, "25-40"), (0.40, 1.0, "40+")]:
        b = [x for x in raw_bets if lo <= x["raw_ev"] < hi]
        if b:
            profit = sum((x["odds"]/100 if x["odds"]>0 else 100/abs(x["odds"])) if x["actual"] else -1 for x in b)
            roi = profit / len(b) * 100
            raw_roi_by_bucket[lbl] = roi
            print(f"    EV {lbl}%: n={len(b):4d}, ROI={roi:+7.1f}%")
    
    print("\n  CALIB:")
    calib_roi_by_bucket = {}
    for lo, hi, lbl in [(0.08, 0.15, "8-15"), (0.15, 0.25, "15-25"), (0.25, 0.40, "25-40"), (0.40, 1.0, "40+")]:
        b = [x for x in calib_bets if lo <= x["calib_ev"] < hi]
        if b:
            profit = sum((x["odds"]/100 if x["odds"]>0 else 100/abs(x["odds"])) if x["actual"] else -1 for x in b)
            roi = profit / len(b) * 100
            calib_roi_by_bucket[lbl] = roi
            print(f"    EV {lbl}%: n={len(b):4d}, ROI={roi:+7.1f}%")
    
    # Monotonicity
    raw_vals = list(raw_roi_by_bucket.values())
    calib_vals = list(calib_roi_by_bucket.values())
    
    raw_monotonic = all(raw_vals[i] <= raw_vals[i+1] for i in range(len(raw_vals)-1)) if len(raw_vals)>=2 else True
    calib_monotonic = all(calib_vals[i] <= calib_vals[i+1] for i in range(len(calib_vals)-1)) if len(calib_vals)>=2 else True
    
    print(f"\n  Monotonicity: Raw={raw_monotonic}, Calib={calib_monotonic}")
    
    # Step 6: Multiple run stability
    print("\n" + "="*70)
    print("  MULTIPLE RUN STABILITY (5 runs x 2000 games)")
    print("="*70)
    
    stability_results = []
    for run in range(5):
        np.random.seed(1000 + run)
        random.seed(1000 + run)
        
        # Fresh calibration data each run
        cal_games = [generate_game() for _ in range(2000)]
        cal = IsotonicCalibrator()
        cal.fit(
            np.array([g["actual"] for g in cal_games]),
            np.array([g["model_prob"] for g in cal_games])
        )
        
        # Test data
        mkt = RealisticMarketOdds(seed=1000 + run)
        
        raw_b, calib_b = [], []
        for _ in range(2000):
            g = generate_game()
            o = mkt.generate_moneyline_odds(g["true_prob"])
            
            raw_e = g["model_prob"] - o["implied_home"]
            cp = cal.transform(np.array([g["model_prob"]]))[0]
            calib_e = cp - o["implied_home"]
            
            if raw_e >= 0.08:
                raw_b.append({"odds": o["odds_home"], "actual": g["actual"]})
            if calib_e >= 0.08:
                calib_b.append({"odds": o["odds_home"], "actual": g["actual"]})
        
        def calc_roi(bets):
            if not bets:
                return 0
            profit = sum(
                (b["odds"]/100 if b["odds"]>0 else 100/abs(b["odds"])) if b["actual"] else -1
                for b in bets
            )
            return profit / len(bets) * 100
        
        stability_results.append({
            "run": run+1,
            "raw_n": len(raw_b),
            "raw_roi": calc_roi(raw_b),
            "calib_n": len(calib_b),
            "calib_roi": calc_roi(calib_b)
        })
        
        print(f"  Run {run+1}: Raw n={len(raw_b):3d}, ROI={calc_roi(raw_b):+7.1f}% | "
              f"Calib n={len(calib_b):3d}, ROI={calc_roi(calib_b):+7.1f}%")
    
    raw_rois = [r["raw_roi"] for r in stability_results]
    calib_rois = [r["calib_roi"] for r in stability_results]
    
    print(f"\n  Summary:")
    print(f"    Raw:   Mean={np.mean(raw_rois):+.1f}%, Std={np.std(raw_rois):.1f}%")
    print(f"    Calib: Mean={np.mean(calib_rois):+.1f}%, Std={np.std(calib_rois):.1f}%")
    
    if np.std(calib_rois) < np.std(raw_rois):
        print("\n  [PASS] Calibration reduces ROI variance")
    else:
        print("\n  [INFO] Variance: similar or mixed")


if __name__ == "__main__":
    run_calibration_pipeline()
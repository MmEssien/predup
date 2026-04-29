"""
Proper Calibration Validation
Train calibrator on same distribution as test, then apply
"""

import numpy as np
import random


class RealisticMarketOdds:
    """Same as before"""
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
        
        if self.rng.random() < self.noise_probability:
            noise = self.rng.uniform(*self.noise_range)
            prob_home_adj = np.clip(prob_home_adj + noise, 0.05, 0.95)
            prob_away_adj = 1 - prob_home_adj
        
        if prob_home_adj >= 0.5:
            odds_home = int(-(prob_home_adj / (1 - prob_home_adj)) * 100)
        else:
            odds_home = int(((1 - prob_home_adj) / prob_home_adj) * 100)
        
        return {"odds_home": odds_home, "implied_home": prob_home_adj}


class IsotonicCalibrator:
    """Simple isotonic calibration"""
    def __init__(self):
        self.bins = np.linspace(0, 1, 11)
        self.bin_outputs = None
        self.is_fitted = False
    
    def fit(self, y_true, y_prob):
        self.bin_outputs = []
        for i in range(10):
            mask = (y_prob >= self.bins[i]) & (y_prob < self.bins[i+1])
            if i == 9:
                mask = (y_prob >= self.bins[i]) & (y_prob <= self.bins[i+1])
            if mask.sum() > 0:
                self.bin_outputs.append(y_true[mask].mean())
            else:
                self.bin_outputs.append(0.5)
        self.bin_outputs = np.array(self.bin_outputs)
        self.is_fitted = True
        return self
    
    def transform(self, y_prob):
        result = np.zeros_like(y_prob)
        for i in range(10):
            mask = (y_prob >= self.bins[i]) & (y_prob < self.bins[i+1])
            if i == 9:
                mask = (y_prob >= self.bins[i]) & (y_prob <= self.bins[i+1])
            result[mask] = self.bin_outputs[i]
        return result


def generate_game():
    """Generate a single game with features and outcome"""
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
    
    # Model prediction with bias (simulating overconfident ensemble)
    model_prob = true_prob + np.random.normal(0, 0.08)  # Bias + noise
    model_prob = np.clip(model_prob, 0.1, 0.9)
    
    return {
        "true_prob": true_prob,
        "model_prob": model_prob,
        "actual": actual_win
    }


def run_proper_calibration_validation():
    print("="*70)
    print("  CALIBRATION VALIDATION - PROPER METHOD")
    print("="*70)
    
    # Set seeds
    np.random.seed(42)
    random.seed(42)
    
    # Generate calibration data (3000 games)
    # This simulates having historical predictions to train calibrator
    print("\n[1] Generating calibration training data (3000 games)...")
    calibrator_data = []
    market = RealisticMarketOdds(seed=42)
    
    for _ in range(3000):
        game = generate_game()
        odds = market.generate_moneyline_odds(game["true_prob"])
        calibrator_data.append({
            "prob": game["model_prob"],
            "actual": game["actual"]
        })
    
    y_prob_cal = np.array([d["prob"] for d in calibrator_data])
    y_true_cal = np.array([d["actual"] for d in calibrator_data])
    
    # Fit calibrator
    print("[2] Fitting isotonic calibrator...")
    calibrator = IsotonicCalibrator()
    calibrator.fit(y_true_cal, y_prob_cal)
    
    # Generate test data (independent, same process)
    print("[3] Generating test data (5000 games)...")
    np.random.seed(99)  # Different seed for test
    random.seed(99)
    market_test = RealisticMarketOdds(seed=99)
    
    test_results = []
    for _ in range(5000):
        game = generate_game()
        odds = market_test.generate_moneyline_odds(game["true_prob"])
        
        raw_prob = game["model_prob"]
        calib_prob = calibrator.transform(np.array([raw_prob]))[0]
        
        test_results.append({
            "raw_prob": raw_prob,
            "calib_prob": calib_prob,
            "implied": odds["implied_home"],
            "actual": game["actual"]
        })
    
    # Analysis
    print("\n--- CALIBRATION QUALITY ---")
    raw_probs = np.array([r["raw_prob"] for r in test_results])
    calib_probs = np.array([r["calib_prob"] for r in test_results])
    actual = np.array([r["actual"] for r in test_results])
    
    buckets = np.linspace(0, 1, 11)
    raw_errs, calib_errs = [], []
    
    for i in range(10):
        mask = (raw_probs >= buckets[i]) & (raw_probs < buckets[i+1])
        if i == 9:
            mask = (raw_probs >= buckets[i]) & (raw_probs <= buckets[i+1])
        
        if mask.sum() > 0:
            raw_errs.append(abs(raw_probs[mask].mean() - actual[mask].mean()))
            calib_errs.append(abs(calib_probs[mask].mean() - actual[mask].mean()))
    
    print(f"Raw calibration error:   {np.mean(raw_errs):.4f}")
    print(f"Calibrated error:        {np.mean(calib_errs):.4f}")
    
    # EV bucket analysis
    print("\n--- EV BUCKET ANALYSIS ---")
    
    raw_bets = []
    calib_bets = []
    
    for r in test_results:
        raw_ev = r["raw_prob"] - r["implied"]
        calib_ev = r["calib_prob"] - r["implied"]
        
        raw_bet = (r["raw_prob"] > 0.60 or r["raw_prob"] < 0.40) and raw_ev >= 0.15
        calib_bet = (r["calib_prob"] > 0.60 or r["calib_prob"] < 0.40) and calib_ev >= 0.15
        
        odds = market_test.generate_moneyline_odds(r["raw_prob"] + 0.3)["odds_home"]
        
        if raw_bet:
            raw_bets.append({"ev": raw_ev, "odds": odds, "actual": r["actual"]})
        if calib_bet:
            calib_bets.append({"ev": calib_ev, "odds": odds, "actual": r["actual"]})
    
    print(f"Raw bets: {len(raw_bets)}, Calib bets: {len(calib_bets)}")
    
    def bucket_roi(bets, label):
        if not bets:
            print(f"  {label}: No bets")
            return {}
        
        ranges = [(0.15, 0.25, "15-25"), (0.25, 0.35, "25-35"), 
                  (0.35, 0.50, "35-50"), (0.50, 1.0, "50+")]
        
        results = {}
        for low, high, lbl in ranges:
            bucket = [b for b in bets if low <= b["ev"] < high]
            if bucket:
                profit = 0
                for b in bucket:
                    if b["actual"]:
                        o = b["odds"]
                        profit += o/100 if o > 0 else 100/abs(o)
                    else:
                        profit -= 1
                roi = profit / len(bucket) * 100
                results[lbl] = roi
                print(f"  {label} EV {lbl}%: n={len(bucket):3d}, ROI={roi:+6.1f}%")
        return results
    
    raw_rois = bucket_roi(raw_bets, "Raw")
    print()
    calib_rois = bucket_roi(calib_bets, "Calib")
    
    # Monotonicity
    def is_monotonic(d):
        vals = list(d.values())
        if len(vals) < 2:
            return True
        return all(vals[i] <= vals[i+1] for i in range(len(vals)-1))
    
    print(f"\n  Monotonic: Raw={is_monotonic(raw_rois)}, Calib={is_monotonic(calib_rois)}")
    
    # Multiple runs
    print("\n" + "="*70)
    print("  MULTIPLE RUN STABILITY TEST (5 runs)")
    print("="*70)
    
    run_results = []
    for run in range(5):
        np.random.seed(100 + run)
        random.seed(100 + run)
        
        mkt = RealisticMarketOdds(seed=100 + run)
        
        # Generate fresh calibration data for this run
        cal_data = []
        for _ in range(2000):
            g = generate_game()
            cal_data.append({"prob": g["model_prob"], "actual": g["actual"]})
        
        cal = IsotonicCalibrator()
        cal.fit(
            np.array([d["actual"] for d in cal_data]),
            np.array([d["prob"] for d in cal_data])
        )
        
        # Generate test for this run
        raw_b, cb = [], []
        for _ in range(2000):
            g = generate_game()
            o = mkt.generate_moneyline_odds(g["true_prob"])
            
            raw_e = g["model_prob"] - o["implied_home"]
            cp = cal.transform(np.array([g["model_prob"]]))[0]
            cb_e = cp - o["implied_home"]
            
            if (g["model_prob"] > 0.60 or g["model_prob"] < 0.40) and raw_e >= 0.15:
                raw_b.append({"odds": o["odds_home"], "actual": g["actual"]})
            if (cp > 0.60 or cp < 0.40) and cb_e >= 0.15:
                cb.append({"odds": o["odds_home"], "actual": g["actual"]})
        
        def calc_roi(bets):
            if not bets:
                return 0
            p = sum(
                (b["odds"]/100 if b["odds"]>0 else 100/abs(b["odds"])) if b["actual"] else -1
                for b in bets
            )
            return p / len(bets) * 100
        
        r_roi = calc_roi(raw_b)
        c_roi = calc_roi(cb)
        
        run_results.append((len(raw_b), r_roi, len(cb), c_roi))
        print(f"  Run {run+1}: Raw n={len(raw_b):3d}, ROI={r_roi:+6.1f}% | Calib n={len(cb):3d}, ROI={c_roi:+6.1f}%")
    
    raw_rois_all = [r[1] for r in run_results]
    calib_rois_all = [r[3] for r in run_results]
    
    print(f"\n  Summary:")
    print(f"    Raw:   AVG={np.mean(raw_rois_all):+.1f}%, STD={np.std(raw_rois_all):.1f}%")
    print(f"    Calib: AVG={np.mean(calib_rois_all):+.1f}%, STD={np.std(calib_rois_all):.1f}%")
    
    if np.std(calib_rois_all) < np.std(raw_rois_all):
        print("\n[PASS] Calibration reduces variance")
    else:
        print("\n[INFO] Variance comparison: mixed")


if __name__ == "__main__":
    run_proper_calibration_validation()
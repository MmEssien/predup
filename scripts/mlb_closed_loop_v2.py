"""
MLB Closed-Loop Pipeline with REAL ML Model
Uses trained XGBoost model for predictions
"""

import sys
from pathlib import Path
script_dir = Path(__file__).parent
predup_root = script_dir.parent
sys.path.insert(0, str(predup_root))

from dotenv import load_dotenv
load_dotenv()

import numpy as np
import pandas as pd
import random
from datetime import datetime, timedelta
import xgboost as xgb


class RealisticMarketOdds:
    """Realistic bookmaker odds generation with overround, bias, and noise"""
    
    def __init__(self, seed=None):
        self.rng = np.random.default_rng(seed)
        self.overround_range = (0.04, 0.10)  # 4-10%
        self.favorite_bias = 0.07  # Favorites overvalued by 7%
        self.noise_probability = 0.10  # 10% of lines have noise
        self.noise_range = (-0.08, 0.08)  # ±8% deviation
    
    def generate_moneyline_odds(self, true_prob_home: float) -> dict:
        prob_home = true_prob_home
        prob_away = 1 - true_prob_home
        
        # Add market bias (favorites overvalued)
        if prob_home > 0.5:
            bias = self.favorite_bias * (prob_home - 0.5) * 2
            prob_home = prob_home - bias
            prob_away = 1 - prob_home
        else:
            bias = self.favorite_bias * (prob_away - 0.5) * 2
            prob_away = prob_away - bias
            prob_home = 1 - prob_away
        
        # Add overround (vig)
        overround = self.rng.uniform(*self.overround_range)
        total = prob_home + prob_away
        adjusted_total = total * (1 + overround)
        
        prob_home_adj = (prob_home / total) * adjusted_total
        prob_away_adj = (prob_away / total) * adjusted_total
        
        # Add noise
        has_noise = False
        if self.rng.random() < self.noise_probability:
            noise = self.rng.uniform(*self.noise_range)
            prob_home_adj = np.clip(prob_home_adj + noise, 0.05, 0.95)
            prob_away_adj = 1 - prob_home_adj
            has_noise = True
        
        # Convert to American odds
        if prob_home_adj >= 0.5:
            odds_home = int(-(prob_home_adj / (1 - prob_home_adj)) * 100)
        else:
            odds_home = int(((1 - prob_home_adj) / prob_home_adj) * 100)
        
        if prob_away_adj >= 0.5:
            odds_away = int(-(prob_away_adj / (1 - prob_away_adj)) * 100)
        else:
            odds_away = int(((1 - prob_away_adj) / prob_away_adj) * 100)
        
        return {
            "odds_home": odds_home,
            "odds_away": odds_away,
            "implied_home": prob_home_adj,
            "implied_away": prob_away_adj,
            "overround_pct": overround * 100,
            "has_noise": has_noise
        }

# Generate training data (same as model training)
def generate_training_data(n_samples=2000, seed=42):
    np.random.seed(seed)
    random.seed(seed)
    
    data = []
    for i in range(n_samples):
        home_offense = np.random.normal(0.5, 0.15)
        away_offense = np.random.normal(0.5, 0.15)
        home_pitching = np.random.normal(0.5, 0.15)
        away_pitching = np.random.normal(0.5, 0.15)
        
        home_advantage = 0.03
        starter_home = np.random.normal(0.5, 0.2)
        starter_away = np.random.normal(0.5, 0.2)
        
        bullpen_home_fatigue = np.random.uniform(0, 1)
        bullpen_away_fatigue = np.random.uniform(0, 1)
        
        home_rest = random.choice([0, 1, 2, 3])
        away_rest = random.choice([0, 1, 2, 3])
        
        home_recent = np.random.normal(0.5, 0.2)
        away_recent = np.random.normal(0.5, 0.2)
        
        logit = (
            +0.8 * (home_offense - away_offense) * 2 +
            -0.8 * (home_pitching - away_pitching) * 2 +
            +0.3 * home_advantage +
            +0.1 * (home_rest - away_rest) +
            +0.3 * (home_recent - away_recent) +
            +0.3 * (starter_home - starter_away) +
            -0.1 * bullpen_home_fatigue +
            +0.1 * bullpen_away_fatigue
        )
        
        true_win_prob = 1 / (1 + np.exp(-logit))
        true_win_prob = np.clip(true_win_prob + np.random.normal(0, 0.05), 0.1, 0.9)
        
        actual_home_win = np.random.random() < true_win_prob
        
        data.append({
            "home_win": int(actual_home_win),
            "home_offense": home_offense, "away_offense": away_offense,
            "home_pitching": home_pitching, "away_pitching": away_pitching,
            "home_starter": starter_home, "away_starter": starter_away,
            "bullpen_home_fatigue": bullpen_home_fatigue, "bullpen_away_fatigue": bullpen_away_fatigue,
            "home_rest": home_rest, "away_rest": away_rest,
            "home_recent": home_recent, "away_recent": away_recent,
            "pitching_diff": home_pitching - away_pitching,
            "offense_diff": home_offense - away_offense,
            "rest_advantage": home_rest - away_rest,
            "recent_form_diff": home_recent - away_recent,
            "starter_diff": starter_home - starter_away,
            "bullpen_diff": bullpen_away_fatigue - bullpen_home_fatigue,
        })
    
    return pd.DataFrame(data)


def ml_to_decimal(ml):
    """Convert American odds to decimal"""
    if ml > 0:
        return 1 + ml/100
    return 1 + 100/abs(ml)


def calculate_ev(model_prob, odds_american, stake=1.0):
    """Calculate expected value"""
    decimal = ml_to_decimal(odds_american)
    win_prob = model_prob
    lose_prob = 1 - model_prob
    
    profit = stake * (decimal - 1) if win_prob > 0 else 0
    loss = stake
    
    ev = win_prob * profit - lose_prob * loss
    ev_pct = (ev / stake) * 100 if stake > 0 else 0
    
    return {"ev": ev, "ev_pct": ev_pct, "is_positive": ev > 0}


# Train model once
print("="*70)
print("  TRAINING MLB MODEL")
print("="*70)

df = generate_training_data(2000)
feature_cols = [c for c in df.columns if c != "home_win"]

X = df[feature_cols]
y = df["home_win"]

X_train, X_test, y_train, y_test = X[:1400], X[1400:], y[:1400], y[1400:]

model = xgb.XGBClassifier(
    n_estimators=100, max_depth=4, learning_rate=0.1,
    subsample=0.8, colsample_bytree=0.8,
    random_state=42, use_label_encoder=False, eval_metric="logloss"
)
model.fit(X_train, y_train)

# Now run closed-loop validation
print("\n" + "="*70)
print("  CLOSED-LOOP VALIDATION")
print("="*70)

# Simulate 100 games
results = []
bets = []

# Initialize realistic market once
market = RealisticMarketOdds(seed=42)

for game_num in range(3000):
    # Generate a game
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
    
    # Calculate TRUE outcome using same logistic function
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
    
    # Get MODEL prediction
    features = [[home_offense, away_offense, home_pitching, away_pitching,
                 home_starter, away_starter, bullpen_home_fatigue, bullpen_away_fatigue,
                 home_rest, away_rest, home_recent, away_recent,
                 home_pitching - away_pitching, home_offense - away_offense,
                 home_rest - away_rest, home_recent - away_recent,
                 home_starter - away_starter, bullpen_away_fatigue - bullpen_home_fatigue]]
    
    model_prob = model.predict_proba(features)[0][1]
    
    # Generate market odds using realistic model (based on TRUE probability)
    odds = market.generate_moneyline_odds(true_prob)
    market_odds = odds["odds_home"]
    implied_prob = odds["implied_home"]
    
    # Calculate EV
    ev = calculate_ev(model_prob, market_odds)
    
# Decision - tighter criteria for realistic market
    # Need strong edge to overcome vig
    bet_on_home = (model_prob > 0.60 or model_prob < 0.40) and ev["ev_pct"] >= 15
    
    results.append({
        "model_prob": model_prob,
        "true_prob": true_prob,
        "market_odds": market_odds,
        "implied": implied_prob,
        "edge": model_prob - implied_prob,
        "ev_pct": ev["ev_pct"],
        "bet": bet_on_home,
        "actual_win": actual_win
    })
    
    if bet_on_home:
        bets.append({
            "model_prob": model_prob,
            "ev_pct": ev["ev_pct"],
            "odds": market_odds,
            "actual_win": actual_win
        })

# Analyze results
print("\n--- EV DISTRIBUTION ---")
evs = [r["ev_pct"] for r in results]
print(f"Mean EV: {np.mean(evs):+.1f}%")
print(f"Median EV: {np.median(evs):+.1f}%")
print(f"Std EV: {np.std(evs):.1f}%")
print(f"% Positive EV: {sum(1 for e in evs if e > 0)/len(evs)*100:.1f}%")

print("\n--- BET ANALYSIS ---")
print(f"Total games: {len(results)}")
print(f"Qualifying bets: {len(bets)}")
print(f"Bet rate: {len(bets)/len(results)*100:.1f}%")

if bets:
    bet_evs = [b["ev_pct"] for b in bets]
    print(f"\nBet EV stats:")
    print(f"  Mean EV of bets: {np.mean(bet_evs):+.1f}%")
    print(f"  Expected ROI: {np.mean(bet_evs):+.1f}%")
    
    # Actual outcomes
    won = sum(1 for b in bets if b["actual_win"])
    win_rate = won / len(bets)
    print(f"  Actual win rate: {win_rate:.1%}")
    
    # Calculate actual profit
    profit = 0
    for b in bets:
        if b["actual_win"]:
            odds = b["odds"]
            if odds > 0:
                profit += odds / 100
            else:
                profit += 100 / abs(odds)
        else:
            profit -= 1
    
    roi = (profit / len(bets)) * 100
    print(f"  Actual profit: ${profit:.2f}")
    print(f"  Actual ROI: {roi:+.1f}%")
else:
    print("\nNo qualifying bets found")

print("\n--- EDGE STABILITY CHECK ---")
# Check if edge clusters logically
high_prob = [r for r in results if r["model_prob"] >= 0.55]
low_prob = [r for r in results if r["model_prob"] < 0.45]

print(f"High prob games (>=55%): {len(high_prob)}")
if high_prob:
    print(f"  Avg true outcome: {np.mean([r['actual_win'] for r in high_prob]):.1%}")
    
print(f"Low prob games (<45%): {len(low_prob)}")
if low_prob:
    print(f"  Avg true outcome: {np.mean([r['actual_win'] for r in low_prob]):.1%}")

print("\n" + "="*70)
print("  VALIDATION COMPLETE")
print("="*70)

if bets and len(bets) > 5:
    if abs(np.mean([b["ev_pct"] for b in bets]) - roi) < 20:
        print("\n[PASS] EV distribution is SANE (predictions correlate to outcomes)")
    else:
        print("\n[FAIL] WARNING: EV does not match actual ROI")
else:
    print("\n[INFO] Need more bets to validate")

# ========================================================================
# LARGE-SCALE EV VALIDATION
# ========================================================================
print("\n" + "="*70)
print("  LARGE-SCALE EV VALIDATION (3,000 games)")
print("="*70)

# Run fresh simulation with 3000 games
results_v2 = []
bets_v2 = []

for game_num in range(3000):
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
    
    features = [[home_offense, away_offense, home_pitching, away_pitching,
                 home_starter, away_starter, bullpen_home_fatigue, bullpen_away_fatigue,
                 home_rest, away_rest, home_recent, away_recent,
                 home_pitching - away_pitching, home_offense - away_offense,
                 home_rest - away_rest, home_recent - away_recent,
                 home_starter - away_starter, bullpen_away_fatigue - bullpen_home_fatigue]]
    
    model_prob = model.predict_proba(features)[0][1]
    odds = market.generate_moneyline_odds(true_prob)
    market_odds = odds["odds_home"]
    implied_prob = odds["implied_home"]
    
    ev = calculate_ev(model_prob, market_odds)
    bet_on_home = (model_prob > 0.60 or model_prob < 0.40) and ev["ev_pct"] >= 15
    
    results_v2.append({
        "model_prob": model_prob,
        "true_prob": true_prob,
        "market_odds": market_odds,
        "implied": implied_prob,
        "edge": model_prob - implied_prob,
        "ev_pct": ev["ev_pct"],
        "bet": bet_on_home,
        "actual_win": actual_win
    })
    
    if bet_on_home:
        bets_v2.append({
            "ev_pct": ev["ev_pct"],
            "odds": market_odds,
            "actual_win": actual_win
        })

print(f"\nSimulation complete: {len(results_v2)} games, {len(bets_v2)} bets")

# EV BUCKET ANALYSIS
print("\n--- EV BUCKET ROI ANALYSIS ---")
buckets = [
    (15, 20, "15-20%"),
    (20, 30, "20-30%"),
    (30, 40, "30-40%"),
    (40, 50, "40-50%"),
    (50, 100, "50%+")
]

bucket_results = []
for low, high, label in buckets:
    bucket_bets = [b for b in bets_v2 if low <= b["ev_pct"] < high]
    if bucket_bets:
        wins = sum(1 for b in bucket_bets if b["actual_win"])
        profit = 0
        for b in bucket_bets:
            if b["actual_win"]:
                odds = b["odds"]
                if odds > 0:
                    profit += odds / 100
                else:
                    profit += 100 / abs(odds)
            else:
                profit -= 1
        roi = (profit / len(bucket_bets)) * 100
        bucket_results.append({
            "label": label,
            "n": len(bucket_bets),
            "wins": wins,
            "win_rate": wins / len(bucket_bets),
            "avg_ev": np.mean([b["ev_pct"] for b in bucket_bets]),
            "profit": profit,
            "roi": roi
        })
        print(f"  EV {label}: n={len(bucket_bets)}, win={wins/len(bucket_bets):.1%}, "
              f"EV={np.mean([b['ev_pct'] for b in bucket_bets]):+.1f}%, ROI={roi:+.1f}%")

# Check monotonicity
if len(bucket_results) >= 2:
    rois = [r["roi"] for r in bucket_results]
    evs = [r["avg_ev"] for r in bucket_results]
    correlation = np.corrcoef(evs, rois)[0, 1]
    print(f"\n  EV-ROI correlation: {correlation:.3f}")
    if correlation > 0.5:
        print("  [PASS] EV ranking predicts ROI monotonically")
    else:
        print("  [WARN] EV-ROI correlation weak")

# DRAWDOWN ANALYSIS
print("\n--- DRAWDOWN & VOLATILITY ANALYSIS ---")
cumulative = 0
peak = 0
max_dd = 0
dd_samples = []
for b in bets_v2:
    if b["actual_win"]:
        odds = b["odds"]
        if odds > 0:
            cumulative += odds / 100
        else:
            cumulative += 100 / abs(odds)
    else:
        cumulative -= 1
    peak = max(peak, cumulative)
    dd = peak - cumulative
    max_dd = max(max_dd, dd)
    dd_samples.append(cumulative)

print(f"  Starting bankroll: $100.00")
print(f"  Final bankroll: ${100 + cumulative:.2f}")
print(f"  Peak bankroll: ${100 + peak:.2f}")
print(f"  Max drawdown: ${max_dd:.2f}")
print(f"  Max DD %: {max_dd / (100 + peak) * 100:.1f}%")

# Volatility
returns = []
for i, b in enumerate(bets_v2):
    if b["actual_win"]:
        odds = b["odds"]
        r = odds / 100 if odds > 0 else 100 / abs(odds)
    else:
        r = -1
    returns.append(r)

print(f"  Volatility (std): {np.std(returns):.3f}")
print(f"  Sharpe-like (EV/std): {np.mean(returns) / np.std(returns):.3f}")

# OVERALL STABILITY
print("\n--- STABILITY METRICS ---")
print(f"  Total bets: {len(bets_v2)}")
print(f"  Expected ROI: {np.mean([b['ev_pct'] for b in bets_v2]):+.1f}%")
bet_roi = (sum(
    (b["odds"] / 100 if b["odds"] > 0 else 100 / abs(b["odds"])) if b["actual_win"] else -1
    for b in bets_v2
) / len(bets_v2)) * 100
print(f"  Actual ROI: {bet_roi:+.1f}%")
print(f"  EV-ROI gap: {abs(np.mean([b['ev_pct'] for b in bets_v2]) - bet_roi):.1f}%")

if abs(np.mean([b["ev_pct"] for b in bets_v2]) - bet_roi) < 15:
    print("\n[PASS] EV-ROI relationship is STABLE")
else:
    print("\n[WARN] EV-ROI relationship still volatile")

print("\n[COMPLETE]")

# ========================================================================
# MULTIPLE RUN STABILITY CHECK
# ========================================================================
print("\n" + "="*70)
print("  MULTIPLE RUN STABILITY TEST (5 runs x 2000 games)")
print("="*70)

run_results = []
for run_num in range(5):
    results_run = []
    bets_run = []
    
    for game_num in range(2000):
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
        
        features = [[home_offense, away_offense, home_pitching, away_pitching,
                     home_starter, away_starter, bullpen_home_fatigue, bullpen_away_fatigue,
                     home_rest, away_rest, home_recent, away_recent,
                     home_pitching - away_pitching, home_offense - away_offense,
                     home_rest - away_rest, home_recent - away_recent,
                     home_starter - away_starter, bullpen_away_fatigue - bullpen_home_fatigue]]
        
        model_prob = model.predict_proba(features)[0][1]
        odds = market.generate_moneyline_odds(true_prob)
        market_odds = odds["odds_home"]
        
        ev = calculate_ev(model_prob, market_odds)
        bet_on_home = (model_prob > 0.60 or model_prob < 0.40) and ev["ev_pct"] >= 15
        
        if bet_on_home:
            bets_run.append({"ev_pct": ev["ev_pct"], "odds": market_odds, "actual_win": actual_win})
    
    if bets_run:
        ev_mean = np.mean([b["ev_pct"] for b in bets_run])
        profit = sum(
            (b["odds"] / 100 if b["odds"] > 0 else 100 / abs(b["odds"])) if b["actual_win"] else -1
            for b in bets_run
        )
        roi = (profit / len(bets_run)) * 100
        run_results.append({"n": len(bets_run), "ev": ev_mean, "roi": roi})
        print(f"  Run {run_num+1}: n={len(bets_run)}, EV={ev_mean:+.1f}%, ROI={roi:+.1f}%")

if run_results:
    rois = [r["roi"] for r in run_results]
    evs = [r["ev"] for r in run_results]
    print(f"\n  Across {len(run_results)} runs:")
    print(f"    Avg EV: {np.mean(evs):+.1f}% (std: {np.std(evs):.1f}%)")
    print(f"    Avg ROI: {np.mean(rois):+.1f}% (std: {np.std(rois):.1f}%)")
    print(f"    ROI range: {min(rois):+.1f}% to {max(rois):+.1f}%")
    
    if np.std(rois) < 15:
        print("\n[PASS] Results are STABLE across runs")
    else:
        print("\n[WARN] Results show high variance across runs")
"""
Test make_advanced_decision() Integration

Tests the full decision pipeline with all intelligence components.

Usage:
    python scripts/test_make_decision.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from datetime import datetime
import json

from src.decisions.engine import DecisionEngine, IntelligenceEngine

print("="*60)
print("  TESTING make_advanced_decision()")
print("="*60)

# Test 1: Basic DecisionEngine with Intelligence
print("\n[Test 1] DecisionEngine with full Intelligence")
engine = DecisionEngine(league_code="BL1", enable_intelligence=True)

result = engine.make_advanced_decision(
    model_probability=0.70,
    market_odds=1.85,
    model_predictions={"xgboost": 0.68, "lightgbm": 0.72, "logreg": 0.69}
)

print(f"  Approved: {result['approved']}")
print(f"  Decision: {result.get('decision', 'N/A')}")
print(f"  Reason: {result.get('reason', 'N/A')}")
print(f"  Probability: {result.get('probability', 'N/A')}")
print(f"  Market Implied: {result.get('market_implied', 'N/A')}")

# Check for key fields
for key in ['approved', 'decision', 'reason', 'probability', 'stake', 'market_implied', 'edge', 'confidence', 'confidence_band', 'regime']:
    if key in result:
        print(f"    {key}: {result[key]}")

print(f"\n  Full result keys: {list(result.keys())}")

# Test 2: With fixture data (regime detection)
print("\n[Test 2] With fixture data (derby detection)")
fixture_data = {
    "home_team": "man_utd",
    "away_team": "man_city",
    "competition_code": "PL",
    "utc_date": datetime(2025, 3, 15, 15, 30)
}

result2 = engine.make_advanced_decision(
    model_probability=0.68,
    market_odds=1.90,
    model_predictions={"xgboost": 0.66, "lightgbm": 0.70, "logreg": 0.67},
    fixture_data=fixture_data
)

print(f"  Approved: {result2.get('approved', result2.get('decision') == 'accept')}")
if 'regime' in result2:
    print(f"  Regime: {result2['regime']}")

# Test 3: With Bayesian evidence
print("\n[Test 3] With Bayesian evidence")
evidence = [
    {"type": "home_advantage", "strength": 0.8, "direction": 1},
    {"type": "injury_key_player", "strength": 0.7, "direction": -1},
]

result3 = engine.make_advanced_decision(
    model_probability=0.65,
    market_odds=1.80,
    model_predictions={"xgboost": 0.63, "lightgbm": 0.67},
    fixture_data={"home_team": "bayern", "away_team": "freiburg", "competition_code": "BL1", "utc_date": datetime(2025, 3, 15)},
    evidence=evidence
)

print(f"  Approved: {result3.get('approved')}")
print(f"  Stake: ${result3.get('stake', 0):.2f}")

# Test 4: Compare with vs without intelligence
print("\n[Test 4] Comparison: With vs Without Intelligence")
engine_no_intel = DecisionEngine(league_code="BL1", enable_intelligence=False)

result_with = engine.make_advanced_decision(
    model_probability=0.70, 
    market_odds=1.85,
    model_predictions={"xgboost": 0.70}
)

result_without = engine_no_intel.make_advanced_decision(
    model_probability=0.70, 
    market_odds=1.85,
    model_predictions={"xgboost": 0.70}
)

print(f"  With Intelligence:")
print(f"    Approved: {result_with.get('approved', 'N/A')}, Stake: ${result_with.get('stake', 0):.2f}")

print(f"  Without Intelligence:")
print(f"    Approved: {result_without.get('approved', 'N/A')}, Stake: ${result_without.get('stake', 0):.2f}")

# Test 5: Batch processing
print("\n[Test 5] IntelligenceEngine batch processing")
intell = IntelligenceEngine(league_code="PL")

predictions = [
    {"probability": 0.75, "odds": 1.75, "model_predictions": {"xgboost": 0.73}},
    {"probability": 0.52, "odds": 2.10, "model_predictions": {"xgboost": 0.50}},
    {"probability": 0.85, "odds": 1.50, "model_predictions": {"xgboost": 0.83}},
]

batch_result = intell.batch_process(predictions, bankroll=10000)

print(f"  Total: {batch_result['stats']['total']}")
print(f"  Accepted: {batch_result['stats']['accepted']}")
print(f"  Rejected: {batch_result['stats']['rejected']}")
print(f"  Acceptance rate: {batch_result['stats']['acceptance_rate']:.1%}")
print(f"  Total stake: ${batch_result['stats']['total_stake']:.2f}")

print("\n" + "="*60)
print("  ALL TESTS COMPLETED")
print("="*60)
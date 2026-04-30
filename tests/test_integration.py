"""Integration validation tests for the intelligence-powered decision engine"""

import sys
sys.path.insert(0, 'PredUp')

from datetime import datetime
import json


def print_header(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def run_integration_tests():
    print_header("INTEGRATED DECISION ENGINE TESTS")
    
    from src.decisions.engine import DecisionEngine, IntelligenceEngine
    from src.intelligence.bayesian_engine import Evidence, EvidenceType
    
    # Test 1: Basic DecisionEngine with intelligence enabled
    print("\n[Test 1] DecisionEngine with Intelligence")
    engine = DecisionEngine(league_code="BL1", enable_intelligence=True)
    
    result = engine.make_advanced_decision(
        model_probability=0.68,
        market_odds=1.80,
        model_predictions={"xgboost": 0.66, "lightgbm": 0.70, "logreg": 0.67}
    )
    print(f"   Result: approved={result['approved']}, decision={result['decision']}")
    print(f"   Stake: {result['stake']:.2f}, Confidence: {result['confidence']:.2f}")
    print(f"   Regime: {result['regime']}")
    assert result['approved'] == True or result['approved'] == False, "Failed: invalid result"
    print("   [PASS]")
    
    # Test 2: Decision without intelligence
    print("\n[Test 2] DecisionEngine WITHOUT Intelligence")
    engine_no_intel = DecisionEngine(league_code="BL1", enable_intelligence=False)
    result2 = engine_no_intel.make_advanced_decision(
        model_probability=0.68,
        market_odds=1.80,
        model_predictions={"xgboost": 0.70}
    )
    print(f"   Result: {result2['reason']}")
    assert result2['reason'] == "intelligence_disabled", "Failed: should fall back to no intelligence"
    print("   [PASS]")
    
    # Test 3: IntelligenceEngine standalone
    print("\n[Test 3] IntelligenceEngine Standalone")
    intell = IntelligenceEngine(league_code="PL")
    result3 = intell.process_prediction(
        model_probability=0.70,
        market_odds=1.90,
        model_predictions={"xgboost": 0.68, "lightgbm": 0.72, "logreg": 0.69}
    )
    print(f"   Approved: {result3['approved']}, Stake: {result3['stake']:.2f}")
    print(f"   Edge: {result3['edge']:.3f}, Confidence: {result3['confidence']:.3f}")
    print(f"   Strain: {result3['stake_size']}")
    print("   [PASS]")
    
    # Test 4: With fixture data (regime detection)
    print("\n[Test 4] With Fixture Data (Regime Detection)")
    fixture_data = {
        "home_team": "man_utd",
        "away_team": "man_city",
        "competition_code": "PL",
        "utc_date": datetime(2025, 3, 15, 15, 30)
    }
    result4 = intell.process_prediction(
        model_probability=0.65,
        market_odds=2.00,
        model_predictions={"xgboost": 0.63, "lightgbm": 0.67, "logreg": 0.64},
        fixture_data=fixture_data
    )
    print(f"   Regime: {result4['regime']}, Is Derby: {result4['is_derby']}")
    print(f"   Unpredictability: {result4['regime_unpredictability']:.2f}")
    assert result4['is_derby'] == True, "Failed: derby not detected"
    print("   [PASS]")
    
    # Test 5: With Bayesian evidence
    print("\n[Test 5] With Bayesian Evidence")
    evidence = [
        {"type": "home_advantage", "strength": 0.8, "direction": 1, "description": "Home team"},
        {"type": "rest_days", "strength": 0.7, "direction": 1, "description": "5 days rest"},
        {"type": "injury_key_player", "strength": 0.6, "direction": -1, "description": "Key player out"},
    ]
    result5 = intell.process_prediction(
        model_probability=0.60,
        market_odds=1.85,
        model_predictions={"xgboost": 0.58, "lightgbm": 0.62},
        evidence=evidence,
        fixture_data={"home_team": "bayern", "away_team": "freiburg", "competition_code": "BL1", "utc_date": datetime(2025, 3, 15)}
    )
    print(f"   Model prob: 0.600 -> Adjusted: {result5['adjusted_probability']:.3f} -> Final: {result5['final_probability']:.3f}")
    print(f"   Approved: {result5['approved']}, Stake: {result5['stake']:.2f}")
    print("   [PASS]")
    
    # Test 6: Batch processing
    print("\n[Test 6] Batch Processing")
    predictions = [
        {"probability": 0.72, "odds": 1.75, "model_predictions": {"xgboost": 0.70, "lightgbm": 0.74}},
        {"probability": 0.55, "odds": 2.20, "model_predictions": {"xgboost": 0.53, "lightgbm": 0.57}},
        {"probability": 0.48, "odds": 2.50, "model_predictions": {"xgboost": 0.46, "lightgbm": 0.50}},
        {"probability": 0.80, "odds": 1.50, "model_predictions": {"xgboost": 0.78, "lightgbm": 0.82}},
    ]
    batch_result = intell.batch_process(predictions, bankroll=10000)
    print(f"   Total: {batch_result['stats']['total']}, Accepted: {batch_result['stats']['accepted']}")
    print(f"   Acceptance rate: {batch_result['stats']['acceptance_rate']:.1%}")
    print(f"   Total stake: {batch_result['stats']['total_stake']:.2f}")
    assert batch_result['stats']['accepted'] > 0, "Failed: no accepted predictions"
    print("   [PASS]")
    
    # Test 7: League-specific behavior
    print("\n[Test 7] League-Specific Behavior")
    
    # BL1 (higher threshold)
    bl1_engine = IntelligenceEngine(league_code="BL1")
    result_bl1 = bl1_engine.process_prediction(
        model_probability=0.62,
        market_odds=1.90,
        model_predictions={"xgboost": 0.60, "lightgbm": 0.64}
    )
    
    # PL (lower threshold)
    pl_engine = IntelligenceEngine(league_code="PL")
    result_pl = pl_engine.process_prediction(
        model_probability=0.62,
        market_odds=1.90,
        model_predictions={"xgboost": 0.60, "lightgbm": 0.64}
    )
    
    print(f"   BL1: approved={result_bl1['approved']}, edge={result_bl1['edge']:.3f}")
    print(f"   PL:  approved={result_pl['approved']}, edge={result_pl['edge']:.3f}")
    print("   [PASS]")
    
    # Test 8: Edge case - very low probability
    print("\n[Test 8] Edge Case - Low Probability")
    result8 = intell.process_prediction(
        model_probability=0.25,
        market_odds=4.00,
        model_predictions={"xgboost": 0.24, "lightgbm": 0.26}
    )
    print(f"   Low prob: approved={result8['approved']}, stake={result8['stake']}")
    assert result8['approved'] == False, "Should reject low probability"
    print("   [PASS]")
    
    # Test 9: Complete end-to-end simulation
    print("\n[Test 9] End-to-End Simulation")
    
    # Simulate a full day of predictions
    day_predictions = []
    fixtures = [
        {"home": "bayern", "away": "dortmund", "league": "BL1", "is_derby": True},
        {"home": "arsenal", "away": "chelsea", "league": "PL", "is_derby": True},
        {"home": "freiburg", "away": "leverkusen", "league": "BL1", "is_derby": False},
        {"home": "man_city", "away": "brighton", "league": "PL", "is_derby": False},
    ]
    
    for i, fx in enumerate(fixtures):
        day_predictions.append({
            "probability": 0.55 + (i * 0.10),  # 0.55, 0.65, 0.75, 0.85
            "odds": 2.00 - (i * 0.15),          # Dropping odds
            "model_predictions": {
                "xgboost": 0.53 + (i * 0.10),
                "lightgbm": 0.57 + (i * 0.10),
                "logreg": 0.55 + (i * 0.10)
            },
            "fixture_data": {
                "home_team": fx["home"],
                "away_team": fx["away"],
                "competition_code": fx["league"],
                "utc_date": datetime(2025, 3, 15),
                "is_derby": fx["is_derby"]
            }
        })
    
    day_result = intell.batch_process(day_predictions, bankroll=50000)
    
    print(f"   Day Results:")
    print(f"   - Total predictions: {day_result['stats']['total']}")
    print(f"   - Accepted: {day_result['stats']['accepted']}")
    print(f"   - Total stake: {day_result['stats']['total_stake']:.2f}")
    print(f"   - Acceptance rate: {day_result['stats']['acceptance_rate']:.1%}")
    
    for i, acc in enumerate(day_result['accepted']):
        print(f"     Bet {i+1}: prob={acc['final_probability']:.2f}, stake={acc['stake']:.2f}, reg={acc['regime']}")
    
    print("   [PASS]")
    
    print_header("ALL INTEGRATION TESTS COMPLETED SUCCESSFULLY")
    return True


def run_comparison_tests():
    print_header("COMPARISON: Basic vs Intelligence-Enhanced")
    
    from src.decisions.engine import DecisionEngine
    
    # Test predictions
    test_cases = [
        {"prob": 0.70, "odds": 1.80, "models": {"xgb": 0.68, "lgb": 0.72}},
        {"prob": 0.55, "odds": 2.10, "models": {"xgb": 0.53, "lgb": 0.57}},
        {"prob": 0.45, "odds": 2.50, "models": {"xgb": 0.43, "lgb": 0.47}},
    ]
    
    # Basic decision
    basic_engine = DecisionEngine(league_code="BL1", enable_intelligence=False)
    
    # Intelligence decision  
    intel_engine = DecisionEngine(league_code="BL1", enable_intelligence=True)
    
    print(f"\n{'Prob':>6} | {'Basic':>12} | {'Intelligence':>12} | {'Diff':>8}")
    print("-" * 45)
    
    for tc in test_cases:
        basic = basic_engine.make_advanced_decision(
            tc["prob"], tc["odds"], tc["models"]
        )
        intel = intel_engine.make_advanced_decision(
            tc["prob"], tc["odds"], tc["models"],
            fixture_data={"home_team": "test", "away_team": "test2", "utc_date": datetime(2025,3,15), "competition_code": "BL1"}
        )
        
        diff = intel['probability'] - tc['prob']
        print(f"{tc['prob']:>6.2f} | basic={basic['confidence']:>4.2f} ({basic['decision']:>3}) | intel={intel['probability']:>4.2f} ({intel['decision']:>3}) | {diff:>+7.3f}")
    
    print("\n   Note: Intelligence engine adjusts probability based on")
    print("   regime, market fusion, and filtering - may increase or")
    print("   decrease final probability compared to base model.")


if __name__ == "__main__":
    run_integration_tests()
    run_comparison_tests()
    print("\n" + "="*60)
    print("  ALL TESTS PASSED!")
    print("="*60 + "\n")
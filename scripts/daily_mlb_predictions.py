"""
MLB Daily Shadow Mode Predictions
Uses real StatsAPI data with simulated fallback
"""

import sys
from pathlib import Path
_root = Path(__file__).parent.parent
sys.path.insert(0, str(_root))

import logging
logging.basicConfig(level=logging.WARNING)

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
import xgboost as xgb

from scripts.mlb_xgboost_model import generate_realistic_dataset
from scripts.mlb_statsapi_features import MLBStatsAPIClient, get_game_features, features_to_array
from scripts.shadow_mode_tracker import ShadowModeTracker
from src.intelligence.the_odds_api import TheOddsAPIProvider

TRACKED_SEASON = 2024
CURRENT_SEASON = 2025


def daily_predictions():
    print("="*70)
    print("  DAILY MLB PREDICTIONS")
    print("="*70)
    
    print("\n[1] Training model on historical data...")
    df = generate_realistic_dataset(2000)
    X = df.drop(["home_win", "true_prob"], axis=1).values
    y = df["home_win"].values
    
    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.1,
        eval_metric="logloss"
    )
    calibrated = CalibratedClassifierCV(model, method="isotonic", cv=5)
    calibrated.fit(X, y)
    print(f"    Model trained on {len(y)} games")
    
    print("\n[2] Fetching live odds...")
    the_odds = TheOddsAPIProvider()
    odds_data = the_odds.get_odds("baseball_mlb", "us")
    the_odds.close()
    
    if not odds_data.get("data"):
        print("    No games found from betting API")
        return
    
    betting_games = odds_data["data"]
    print(f"    Found {len(betting_games)} games from FanDuel")
    
    print("\n[3] Fetching real game data from StatsAPI...")
    client = MLBStatsAPIClient(use_cache=True)
    statsapi_games = client.get_todays_games()
    print(f"    Found {len(statsapi_games)} games from StatsAPI")
    client.close()
    
    print("\n[4] Processing predictions...")
    tracker = ShadowModeTracker()
    
    real_data_count = 0
    simulated_count = 0
    
    processed = []
    
    for bet_game in betting_games:
        home_team = bet_game.get("home_team", "")
        away_team = bet_game.get("away_team", "")
        
        match = None
        for sg in statsapi_games:
            sg_teams = sg.get("teams", {})
            sg_home = sg_teams.get("home", {}).get("team", {}).get("name", "")
            sg_away = sg_teams.get("away", {}).get("team", {}).get("name", "")
            
            if sg_home == home_team and sg_away == away_team:
                match = sg
                break
            if home_team in sg_home or away_team in sg_away:
                match = sg
                break
        
        if match:
            features = get_game_features(client, match, season=TRACKED_SEASON)
        else:
            features = None
        
        if features is None:
            print(f"    WARNING: No game data for {home_team} vs {away_team}")
            continue
        
        data_source = features.get("data_source", "simulated")
        if data_source == "statsapi":
            real_data_count += 1
        else:
            simulated_count += 1
        
        feat_array = features_to_array(features)
        prob = calibrated.predict_proba([feat_array])[0, 1]
        
        bookmakers = bet_game.get("bookmakers", [])
        if not bookmakers:
            continue
        
        bm = bookmakers[0]
        for market in bm.get("markets", []):
            if market.get("key") == "h2h":
                home_odds = None
                away_odds = None
                for o in market.get("outcomes", []):
                    if o.get("name") == home_team:
                        home_odds = o.get("price")
                    elif o.get("name") == away_team:
                        away_odds = o.get("price")
                
                home_ev = prob * (home_odds - 1) - (1 - prob) if home_odds else None
                away_ev = (1 - prob) * (away_odds - 1) - prob if away_odds else None
                
                home_ev_pct = home_ev * 100 if home_ev else None
                away_ev_pct = away_ev * 100 if away_ev else None
                
                processed.append({
                    "home": home_team,
                    "away": away_team,
                    "home_pitcher": features.get("home_pitcher", "TBD"),
                    "away_pitcher": features.get("away_pitcher", "TBD"),
                    "home_era": features.get("home_era"),
                    "away_era": features.get("away_era"),
                    "home_ops": features.get("home_ops"),
                    "away_ops": features.get("away_ops"),
                    "prob": prob,
                    "home_odds": home_odds,
                    "away_odds": away_odds,
                    "home_implied": 1/home_odds if home_odds else None,
                    "away_implied": 1/away_odds if away_odds else None,
                    "home_ev": home_ev_pct,
                    "away_ev": away_ev_pct,
                    "data_source": data_source,
                    "bet_on": None,
                    "bet_odds": None,
                    "bet_ev": None
                })
                
                if home_ev_pct and home_ev_pct >= 5.0:
                    processed[-1]["bet_on"] = "home"
                    processed[-1]["bet_odds"] = home_odds
                    processed[-1]["bet_ev"] = home_ev_pct
                elif away_ev_pct and away_ev_pct >= 5.0:
                    processed[-1]["bet_on"] = "away"
                    processed[-1]["bet_odds"] = away_odds
                    processed[-1]["bet_ev"] = away_ev_pct
    
    print(f"\n[5] Results:")
    print(f"    Games processed: {len(processed)}")
    print(f"    Real StatsAPI data: {real_data_count}")
    print(f"    Simulated fallback: {simulated_count}")
    
    if simulated_count > 0:
        print(f"\n    NOTE: {simulated_count} games used SIMULATED features")
        print(f"          ROI/edge claims NOT valid for these games")
    
    print("\n" + "-"*70)
    print(f"  ALL GAMES ({len(processed)})")
    print("-"*70)
    
    for g in processed:
        source_flag = " [SIM]" if g["data_source"] == "simulated" else ""
        print(f"\n  {g['home']} vs {g['away']}{source_flag}")
        print(f"    Pitchers: {g['home_pitcher']} (ERA {g['home_era']:.2f}) vs {g['away_pitcher']} (ERA {g['away_era']:.2f})")
        print(f"    Team OPS: {g['home_ops']:.3f} vs {g['away_ops']:.3f}")
        print(f"    Model prob: {g['prob']:.1%}")
        print(f"    Home odds: {g['home_odds']} (implied {g['home_implied']:.1%}) | EV: {g['home_ev']:+.1f}%")
        print(f"    Away odds: {g['away_odds']} (implied {g['away_implied']:.1%}) | EV: {g['away_ev']:+.1f}%")
        
        if g["bet_on"]:
            print(f"    >>> BET on {g['bet_on'].upper()} at {g['bet_odds']} (EV: {g['bet_ev']:+.1f}%) <<<")
            
            if g['data_source'] == 'statsapi':
                tracker.add_prediction({
                    "game_id": f"{g['home']}_vs_{g['away']}",
                    "home": g['home'],
                    "away": g['away'],
                    "prob": g['prob'],
                    "implied": g['home_implied'] if g["bet_on"] == "home" else g['away_implied'],
                    "odds": g['bet_odds'],
                    "ev_pct": g['bet_ev'],
                    "bet_on": 1 if g["bet_on"] == "home" else 0,
                    "data_source": "statsapi"
                })
    
    print("\n" + "-"*70)
    qualifying = [g for g in processed if g["bet_on"]]
    real_qualifying = [g for g in qualifying if g["data_source"] == "statsapi"]
    
    print(f"  QUALIFYING BETS (EV >= 5%): {len(qualifying)}")
    print(f"    With real data: {len(real_qualifying)}")
    print(f"    With simulated: {len(qualifying) - len(real_qualifying)}")
    print("-"*70)
    
    if real_qualifying:
        print("\n  QUALIFYING BETS WITH REAL DATA:")
        for g in real_qualifying:
            print(f"    {g['home']} vs {g['away']}: Bet {g['bet_on']} @ {g['bet_odds']} (EV: {g['bet_ev']:+.1f}%)")
    
    print("\n" + "="*70)
    
    return processed


if __name__ == "__main__":
    daily_predictions()
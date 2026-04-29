"""
NBA Daily Predictions - Prediction engine for live NBA games
Integrates shadow mode tracking for paper trading validation
"""

import sys
from pathlib import Path
_root = Path(r"C:\Users\Strategic Shelter\.antigravity\AI\PredUp")
sys.path.insert(0, str(_root))

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dotenv import load_dotenv

load_dotenv(_root / ".env")
logger = logging.getLogger(__name__)


def load_nba_model():
    """Load or train NBA model"""
    from src.models.nba_model import NBAModelTrainer, NBAModelConfig
    
    # Check for existing model
    model_path = _root / "models" / "nba_model.pkl"
    if model_path.exists():
        try:
            import pickle
            with open(model_path, "rb") as f:
                return pickle.load(f)
        except Exception as e:
            logger.warning(f"Could not load model: {e}")
    
    # Train new model with historical data
    logger.info("Training new NBA model...")
    from src.data.nba_client import NBAApiSportsClient
    from src.data.nba_adapter import NBAAdapter
    
    client = NBAApiSportsClient(os.getenv("NBA_API_KEY", ""))
    adapter = NBAAdapter(os.getenv("NBA_API_KEY"))
    
    # Load games
    games = []
    for season in [2023, 2024]:
        data = client.get_games(season=season)
        games.extend(data.get("response", []))
    
    if len(games) < 100:
        logger.warning(f"Insufficient games: {len(games)}")
        client.close()
        return None
    
    client.close()
    
    # Extract standings and injuries
    standings = adapter.get_standings()
    injuries = adapter.get_injuries()
    team_stats = {}
    
    # For now, use simple stats extraction
    trainer = NBAModelTrainer()
    
    return trainer


def get_nba_games_today() -> List[Dict]:
    """Get today's NBA games"""
    from src.data.nba_adapter import NBAAdapter
    from src.data.nba_client import get_current_nba_season
    
    adapter = NBAAdapter(os.getenv("NBA_API_KEY"))
    
    # Get current season games
    season = get_current_nba_season()
    data = adapter.client.get_games(season=season)
    
    games = data.get("response", [])
    
    # Filter for today's games
    today = datetime.now().date()
    todays_games = []
    
    for g in games:
        try:
            game_date = datetime.fromisoformat(g.get("date", "")[:10]).date()
            if game_date == today:
                todays_games.append(g)
        except:
            pass
    
    adapter.close()
    return todays_games


def predict_game(game: Dict, team_stats: Dict, odds_data: Dict, injuries: Dict, trainer) -> Dict:
    """Generate prediction for a single game"""
    from src.data.nba_adapter import NBAAdapter
    from src.data.nba_client import get_current_nba_season
    
    home_team = game.get("teams", {}).get("home", {})
    away_team = game.get("teams", {}).get("away", {})
    
    home_id = home_team.get("id")
    away_id = away_team.get("id")
    
    if trainer is None or not trainer.is_trained:
        # Use simple model before training
        # For demo, use win pct differential
        home_pct = 0.5
        away_pct = 0.5
        
        model_prob = home_pct / (home_pct + away_pct)
    else:
        prediction = trainer.predict(
            game,
            team_stats,
            [],
            odds_data.get(game.get("id")),
            injuries
        )
        model_prob = prediction.get("home_win_prob", 0.5)
    
    return {
        "game_id": str(game.get("id")),
        "home_team": home_team.get("name", ""),
        "away_team": away_team.get("name", ""),
        "model_prob": model_prob,
        "start_time": game.get("date", "")
    }


def calculate_ev(model_prob: float, odds: float) -> tuple:
    """Calculate expected value"""
    if odds is None or odds <= 1:
        return 0, 0
    
    implied_prob = 1 / odds
    edge = model_prob - implied_prob
    ev = model_prob * (odds - 1) - (1 - model_prob)
    
    return edge, ev


def run_daily_predictions():
    """Run daily NBA predictions"""
    
    print("="*70)
    print("  NBA DAILY PREDICTIONS")
    print(f"  {datetime.now().strftime('%Y-%m-%d')}")
    print("="*70)
    
    # Load games
    print("\n[1] Loading today's games...")
    games = get_nba_games_today()
    
    if not games:
        print("  No games found today")
        return
    
    print(f"  Found {len(games)} games")
    
    # Load model
    print("\n[2] Loading model...")
    trainer = load_nba_model()
    
    if trainer and trainer.is_trained:
        print("  Model loaded and ready")
    else:
        print("  Using simple probability model")
    
    # Load odds
    print("\n[3] Loading odds...")
    from src.data.nba_odds_adapter import NBAOddsAdapter
    
    odds_adapter = NBAOddsAdapter()
    
    if odds_adapter.is_available():
        print("  Using real odds from The Odds API")
    else:
        print("  Using simulated odds")
    
    # Generate predictions
    print("\n[4] Generating predictions...")
    
    predictions = []
    shadow_tracker = None
    
    for game in games:
        home = game.get("teams", {}).get("home", {}).get("name", "")
        away = game.get("teams", {}).get("away", {}).get("name", "")
        
        # Get odds
        odds_result = odds_adapter.get_odds(home, away)
        
        if not odds_result.get("home_odds"):
            home_odds = 1.91
            away_odds = 1.91
        else:
            home_odds = odds_result["home_odds"]
            away_odds = odds_result["away_odds"]
        
        # Generate prediction
        prediction = predict_game(game, {}, {}, {}, trainer)
        model_prob = prediction["model_prob"]
        
        # Calculate EV
        if model_prob > 0.5:
            edge, ev = calculate_ev(model_prob, home_odds)
            bet_on = "home"
            bet_odds = home_odds
        else:
            edge, ev = calculate_ev(1 - model_prob, away_odds)
            bet_on = "away"
            bet_odds = away_odds
        
        ev_pct = ev * 100
        
        predictions.append({
            "game": f"{home} vs {away}",
            "home": home,
            "away": away,
            "bet_on": bet_on,
            "model_prob": model_prob,
            "odds": bet_odds,
            "edge": edge,
            "ev_pct": ev_pct,
            "decision": "bet" if ev_pct >= 3 else "no_bet"
        })
        
        print(f"  {home} vs {away}")
        print(f"    Prob: {model_prob:.1%}, Odds: {bet_odds}, EV: {ev_pct:+.1f}%")
        print(f"    Decision: {predictions[-1]['decision']}")
    
    # Summary
    print("\n[5] Summary")
    bets_placed = sum(1 for p in predictions if p["decision"] == "bet")
    print(f"  Bets to place: {bets_placed}/{len(predictions)}")
    
    # Save predictions to shadow tracker
    if bets_placed > 0:
        print("\n[6] Saving to shadow mode...")
        
        try:
            from scripts.nba_shadow_mode import NBAShadowTracker
            shadow_tracker = NBAShadowTracker()
            
            for p in predictions:
                if p["decision"] == "bet":
                    shadow_tracker.add_prediction(
                        game_id=p["game"],
                        home_team=p["home"],
                        away_team=p["away"],
                        bet_on=p["bet_on"],
                        model_prob=p["model_prob"],
                        odds=p["odds"],
                        ev_pct=p["ev_pct"],
                        edge=p["edge"]
                    )
            
            print("  Predictions saved to shadow mode")
            
            # Show current shadow mode stats
            summary = shadow_tracker.get_summary()
            if summary["completed"] > 0:
                print(f"\n  Shadow mode: {summary['completed']} completed, ROI: {summary['actual_roi']:+.1f}%")
        
        except Exception as e:
            print(f"  Could not save to shadow mode: {e}")
    
    odds_adapter.close()
    
    return predictions


def main():
    """Main entry point"""
    return run_daily_predictions()


if __name__ == "__main__":
    main()
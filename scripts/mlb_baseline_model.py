"""
MLB Feature Engineering Pipeline
Builds training dataset from StatsAPI data
"""

import sys
from pathlib import Path
_root = Path(r"C:\Users\Strategic Shelter\.antigravity\AI\PredUp")
sys.path.insert(0, str(_root))

import os
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import httpx
from dotenv import load_dotenv

load_dotenv(_root / ".env")
logger = logging.getLogger(__name__)


class MLBStatsClient:
    """Enhanced MLB StatsAPI client with feature data"""
    
    def __init__(self):
        self.base_url = "https://statsapi.mlb.com/api/v1"
        self._client: Optional[httpx.Client] = None
    
    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=30)
        return self._client
    
    def close(self):
        if self._client:
            self._client.close()
            self._client = None
    
    def get_schedule(self, start_date: str, end_date: str) -> List[Dict]:
        """Get schedule for date range"""
        try:
            resp = self.client.get(
                f"{self.base_url}/schedule",
                params={
                    "sportId": 1,
                    "startDate": start_date,
                    "endDate": end_date,
                    "hydrate": "probablePitcher,team,batter, pitcher"
                }
            )
            resp.raise_for_status()
            data = resp.json()
            
            games = []
            for date_obj in data.get("dates", []):
                for game in date_obj.get("games", []):
                    if game.get("gameType") == "R":  # Regular season only
                        games.append(game)
            return games
        except Exception as e:
            logger.error(f"Get schedule error: {e}")
            return []
    
    def get_game_stats(self, game_pk: int) -> Dict:
        """Get detailed game stats"""
        try:
            resp = self.client.get(f"{self.base_url}/game/{game_pk}/boxscore")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Get game stats error: {e}")
            return {}
    
    def get_team_stats_season(self, team_id: int, season: int) -> Dict:
        """Get team season stats"""
        try:
            resp = self.client.get(
                f"{self.base_url}/teams/{team_id}",
                params={"season": season}
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Get team stats error: {e}")
            return {}
    
    def get_player_stats(self, person_id: int, season: int) -> Dict:
        """Get pitcher stats for season"""
        try:
            resp = self.client.get(
                f"{self.base_url}/people/{person_id}/stats",
                params={
                    "stats": "season",
                    "season": season,
                    "group": "pitching"
                }
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Get player stats error: {e}")
            return {}


def parse_pitcher_stats(player_data: Dict) -> Dict:
    """Parse pitcher stats from player data"""
    stats = player_data.get("stats", [])
    if not stats:
        return {
            "era": 4.50,
            "whip": 1.35,
            "k_rate": 0.20,
            "whip": 1.35,
            "ip": 0,
            "so": 0,
            "bb": 0,
            "hr": 0
        }
    
    # Get pitching stats
    pitching = stats[0].get("splits", [])
    if pitching:
        s = pitching[0].get("stat", {})
        ip = float(s.get("inningsPitched", "0").split(".")[0]) if s.get("inningsPitched") else 0
        return {
            "era": float(s.get("era", 4.50) or 4.50),
            "whip": float(s.get("whip", 1.35) or 1.35),
            "ip": ip,
            "so": int(s.get("strikeOuts", 0) or 0),
            "bb": int(s.get("walks", 0) or 0),
            "hr": int(s.get("homeRuns", 0) or 0),
            "games": int(s.get("gamesPitched", 0) or 0)
        }
    
    return {
        "era": 4.50,
        "whip": 1.35,
        "ip": 0,
        "so": 0,
        "bb": 0,
        "hr": 0,
        "games": 0
    }


def build_game_features(game: Dict, stats: Dict) -> Dict:
    """Build feature vector for a game"""
    
    teams = stats.get("teams", {})
    home_data = teams.get("home", {})
    away_data = teams.get("away", {})
    
    home_team_id = home_data.get("team", {}).get("id")
    away_team_id = away_data.get("team", {}).get("id")
    
    home_score = home_data.get("teamStats", {}).get("batting", {}).get("runs", 0)
    away_score = away_data.get("teamStats", {}).get("batting", {}).get("runs", 0)
    
    # Determine winner
    home_win = 1 if home_score > away_score else 0
    
    # Get pitcher data
    home_pitcher = home_data.get("pitchers", {}).get("expected", {})
    away_pitcher = away_data.get("pitchers", {}).get("expected", {})
    
    return {
        "game_pk": stats.get("gamePk"),
        "date": game.get("gameDate"),
        "home_team_id": home_team_id,
        "away_team_id": away_team_id,
        "home_team_name": home_data.get("team", {}).get("name"),
        "away_team_name": away_data.get("team", {}).get("name"),
        "home_score": home_score,
        "away_score": away_score,
        "home_win": home_win,
        "home_pitcher_id": home_pitcher.get("id"),
        "away_pitcher_id": away_pitcher.get("id"),
        "home_pitcher_name": home_pitcher.get("fullName"),
        "away_pitcher_name": away_pitcher.get("fullName")
    }


class FeatureEngineer:
    """MLB feature engineering"""
    
    def __init__(self):
        self.client = MLBStatsClient()
    
    def build_dataset(self, start_date: str, end_date: str, n_games: int = 500) -> List[Dict]:
        """Build training dataset from historical games"""
        
        print(f"Building MLB dataset from {start_date} to {end_date}...")
        
        # Get games
        games = self.client.get_schedule(start_date, end_date)
        print(f"  Found {len(games)} games")
        
        # Build features for each game
        dataset = []
        
        for game in games[:n_games]:
            game_pk = game.get("gamePk")
            if not game_pk:
                continue
            
            # Get detailed stats
            stats = self.client.get_game_stats(game_pk)
            if not stats:
                continue
            
            # Build features
            features = build_game_features(game, stats)
            
            # Add basic batting stats
            teams = stats.get("teams", {})
            for side in ["home", "away"]:
                team_stats = teams.get(side, {}).get("teamStats", {}).get("batting", {})
                features[f"{side}_runs"] = int(team_stats.get("runs", 0) or 0)
                features[f"{side}_hits"] = int(team_stats.get("hits", 0) or 0)
                features[f"{side}_ops"] = float(team_stats.get("ops", 0.700) or 0.700)
                features[f"{side}_avg"] = float(team_stats.get("avg", 0.250) or 0.250)
            
            dataset.append(features)
        
        print(f"  Built {len(dataset)} game records")
        
        self.client.close()
        return dataset
    
    def compute_team_features(self, team_id: int, recent_games: List[Dict]) -> Dict:
        """Compute team-level features from recent games"""
        
        home_games = [g for g in recent_games if g.get("home_team_id") == team_id]
        away_games = [g for g in recent_games if g.get("away_team_id") == team_id]
        
        # Home record
        home_wins = sum(1 for g in home_games if g.get("home_win") == 1 and g.get("home_team_id") == team_id)
        home_losses = len(home_games) - home_wins
        
        # Away record
        away_wins = sum(1 for g in away_games if g.get("away_win") == 0 and g.get("away_team_id") == team_id)
        away_losses = len(away_games) - away_wins
        
        # Recent form (last 10 games)
        recent = home_games + away_games
        recent = sorted(recent, key=lambda x: x.get("date", ""), reverse=True)[:10]
        
        recent_wins = 0
        runs_scored = 0
        runs_allowed = 0
        for g in recent:
            if g.get("home_team_id") == team_id:
                runs_scored += g.get("home_score", 0)
                runs_allowed += g.get("away_score", 0)
                if g.get("home_win") == 1:
                    recent_wins += 1
            else:
                runs_scored += g.get("away_score", 0)
                runs_allowed += g.get("home_score", 0)
                if g.get("away_win") == 1:
                    recent_wins += 1
        
        games_played = len(recent) or 1
        
        return {
            "home_wins": home_wins,
            "home_losses": home_losses,
            "away_wins": away_wins,
            "away_losses": away_losses,
            "recent_form": recent_wins / games_played,
            "run_differential": runs_scored - runs_allowed,
            "runs_per_game": runs_scored / games_played,
            "runs_allowed_per_game": runs_allowed / games_played
        }


def create_baseline_model():
    """Create baseline logistic regression model for MLB"""
    
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
    
    print("="*70)
    print("  MLB BASELINE MODEL (LOGISTIC REGRESSION)")
    print("="*70)
    
    # Simulated training data for MVP
    # In production: fetch real StatsAPI data
    np.random.seed(42)
    n = 1000
    
    # Features: pitcher strength, team offense, defense, situational
    data = {
        "home_era": np.random.normal(4.0, 1.5, n),  # ERA (lower is better)
        "away_era": np.random.normal(4.0, 1.5, n),
        "home_ops": np.random.normal(0.750, 0.100, n),  # OPS (higher is better)
        "away_ops": np.random.normal(0.750, 0.100, n),
        "home_rest": np.random.choice([0, 1, 2, 3], n),  # Days rest
        "away_rest": np.random.choice([0, 1, 2, 3], n),
        "home_recent": np.random.random(n),  # Recent form (0-1)
        "away_recent": np.random.random(n),
        "home_run_diff": np.random.normal(0, 2, n),  # Run differential
        "away_run_diff": np.random.normal(0, 2, n),
        "home_home_adv": np.random.uniform(-0.03, 0.05, n),  # Home advantage
    }
    
    # Create feature matrix
    X = np.column_stack([
        5 - data["home_era"],  # Invert ERA (higher = better pitcher)
        5 - data["away_era"],
        data["home_ops"],
        data["away_ops"],
        data["home_rest"],
        data["away_rest"],
        data["home_recent"],
        data["away_recent"],
        data["home_run_diff"],
        data["away_run_diff"],
        data["home_home_adv"]
    ])
    
    # True win probability (logistic function)
    logit = (
        +0.5 * (X[:, 0] - X[:, 1]) +  # Pitching advantage
        +0.3 * (X[:, 2] - X[:, 3]) +  # Offense advantage
        +0.1 * (X[:, 4] - X[:, 5]) +  # Rest advantage
        +0.2 * (X[:, 6] - X[:, 7]) +  # Recent form
        +0.1 * (X[:, 8] - X[:, 9]) +  # Run differential
        +X[:, 10]  # Home advantage
    )
    
    true_prob = 1 / (1 + np.exp(-logit))
    
    # Generate outcomes
    y_true = (np.random.random(n) < true_prob).astype(int)
    y_prob = true_prob + np.random.normal(0, 0.1, n)  # Add some noise
    y_prob = np.clip(y_prob, 0.1, 0.9)
    
    # Train/validation split
    X_train, X_val, y_train, y_val, prob_train, prob_val = train_test_split(
        X, y_true, y_prob, test_size=0.2, random_state=42
    )
    
    # Train logistic regression
    print("\n[1] Training Logistic Regression...")
    model = LogisticRegression(C=1.0, max_iter=1000, random_state=42)
    model.fit(X_train, y_train)
    
    # Get calibrated probabilities
    print("[2] Calibrating with isotonic regression...")
    calibrated = CalibratedClassifierCV(model, method="isotonic", cv=5)
    calibrated.fit(X_train, y_train)
    
    # Predict on validation set
    y_pred_prob = calibrated.predict_proba(X_val)[:, 1]
    
    # Metrics
    print("\n[3] Validation Metrics")
    
    # Brier score (calibration)
    brier = brier_score_loss(y_val, y_pred_prob)
    print(f"  Brier Score: {brier:.4f} (lower is better, 0.25 = random)")
    
    # Log loss
    ll = log_loss(y_val, y_pred_prob)
    print(f"  Log Loss: {ll:.4f} (lower is better)")
    
    # AUC-ROC
    try:
        auc = roc_auc_score(y_val, y_pred_prob)
        print(f"  AUC-ROC: {auc:.4f}")
    except:
        print("  AUC-ROC: N/A")
    
    # Calibration curve
    print("\n[4] Calibration Check")
    bins = [(0, 0.3), (0.3, 0.4), (0.4, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 1.0)]
    for low, high in bins:
        mask = (y_pred_prob >= low) & (y_pred_prob < high)
        if mask.sum() > 0:
            pred = y_pred_prob[mask].mean()
            actual = y_val[mask].mean()
            print(f"  {low:.0%}-{high:.0%}: pred={pred:.1%}, actual={actual:.1%}, n={mask.sum()}")
    
    # Feature importance
    print("\n[5] Feature Coefficients")
    feature_names = [
        "Home Pitching (ERA)",
        "Away Pitching (ERA)",
        "Home OPS",
        "Away OPS",
        "Home Rest",
        "Away Rest",
        "Home Recent Form",
        "Away Recent Form",
        "Home Run Diff",
        "Away Run Diff",
        "Home Advantage"
    ]
    for name, coef in zip(feature_names, model.coef_[0]):
        print(f"  {name}: {coef:+.3f}")
    
    return model, calibrated


def integrate_with_live_pipeline():
    """Show how to integrate model with live odds pipeline"""
    
    print("\n" + "="*70)
    print("  INTEGRATION WITH LIVE BETTING PIPELINE")
    print("="*70)
    
    print("""
The model integration points:

1. PREDICTION
   Input: Current pitcher stats, team stats, situational factors
   Output: Home win probability (calibrated)
   
2. EV CALCULATION  
   Input: Model probability, Market odds
   Output: EV%, Edge, Kelly fraction
   
3. BET DECISION
   Input: EV threshold (e.g., 3%)
   Output: Bet or Pass
   
4. SHADOW MODE
   Track predictions vs outcomes
   Compute actual ROI vs expected ROI
   
Next steps for real data integration:
1. Fetch pitcher stats from StatsAPI
2. Fetch team stats from StatsAPI
3. Build historical dataset (2024 season)
4. Train model on real features
5. Plug calibrated model into pipeline
""")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Create baseline model (simulated features for MVP)
    model, calibrated = create_baseline_model()
    
    # Show integration points
    integrate_with_live_pipeline()
    
    print("\n" + "="*70)
    print("  PHASE 2 MVP COMPLETE")
    print("="*70)
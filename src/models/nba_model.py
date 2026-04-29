"""NBA Model Training and Prediction

Baseline model: Logistic Regression with XGBoost for NBA moneyline prediction.
With calibration layer for improved probability estimates.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, roc_auc_score, brier_score_loss
import xgboost as xgb

logger = logging.getLogger(__name__)

from src.features.nba_features import NBAFeatureEngine
from src.intelligence.calibration_layer import EVCalibrator


class NBAModelConfig:
    """NBA model configuration"""
    
    # Default feature set
    DEFAULT_FEATURES = [
        "home_win_pct", "away_win_pct",
        "home_off_rtg", "away_off_rtg",
        "home_def_rtg", "away_def_rtg",
        "home_net_rtg", "away_net_rtg",
        "home_pace", "away_pace",
        "home_rest_days", "away_rest_days",
        "home_b2b", "away_b2b",
        "home_is_hot", "away_is_hot",
        "home_is_cold", "away_is_cold",
        "rest_advantage", "home_form_advantage",
        "home_implied_prob", "away_implied_prob",
        "home_key_missing", "away_key_missing",
        "home_injury_impact", "away_injury_impact",
    ]
    
    # Target
    TARGET = "home_win"
    
    # Thresholds for betting
    DEFAULT_THRESHOLD = 0.55
    MIN_EDGE = 0.03


class NBAModelTrainer:
    """Train NBA prediction models"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or NBAModelConfig()
        self.models = {}
        self.feature_names = self.config.DEFAULT_FEATURES
        self.is_trained = False
        self.calibrator: Optional[EVCalibrator] = None
    
    def prepare_training_data(
        self,
        games: List[Dict],
        team_stats: Dict,
        standings: List[Dict],
        odds_data: Optional[Dict] = None,
        injuries: Optional[Dict] = None
    ) -> pd.DataFrame:
        """Prepare training data from games"""
        
        engine = NBAFeatureEngine()
        features_list = []
        targets = []
        
        for game in games:
            # Skip incomplete games
            if game.get("status") != "Finished":
                continue
            
            home_team_id = game.get("home_team", {}).get("id")
            away_team_id = game.get("away_team", {}).get("id")
            
            # Get team stats for this game (use season stats)
            home_stats = team_stats.get(home_team_id, {})
            away_stats = team_stats.get(away_team_id, {})
            
            # Get odds for this game
            home_odds = None
            away_odds = None
            if odds_data:
                game_odds = odds_data.get(game.get("event_id"))
                if game_odds:
                    home_odds = game_odds.get("moneyline", {}).get("home")
                    away_odds = game_odds.get("moneyline", {}).get("away")
            
            # Get injuries
            game_date = datetime.fromisoformat(game.get("start_time", datetime.now().isoformat()))
            h_missing = injuries.get(home_team_id, []) if injuries else []
            a_missing = injuries.get(away_team_id, []) if injuries else []
            
            # Generate features
            features = engine.generate_all_features(
                home_team_id=home_team_id,
                away_team_id=away_team_id,
                home_stats=home_stats,
                away_stats=away_stats,
                standings=standings,
                home_odds=home_odds,
                away_odds=away_odds,
                home_missing=h_missing,
                away_missing=a_missing,
                game_date=game_date
            )
            
            # Filter to known features
            filtered_features = {k: v for k, v in features.items() 
                             if k in self.feature_names}
            
            # Determine target
            home_score = game.get("home_team", {}).get("score", 0)
            away_score = game.get("away_team", {}).get("score", 0)
            target = 1 if home_score > away_score else 0
            
            features_list.append(filtered_features)
            targets.append(target)
        
        df = pd.DataFrame(features_list)
        df[self.config.TARGET] = targets
        
        return df
    
    def train(
        self,
        games: List[Dict],
        team_stats: Dict,
        standings: List[Dict],
        odds_data: Optional[Dict] = None,
        injuries: Optional[Dict] = None,
        test_size: float = 0.3
    ) -> Dict[str, Any]:
        """Train NBA models"""
        
        # Prepare data
        df = self.prepare_training_data(
            games, team_stats, standings, odds_data, injuries
        )
        
        if len(df) < 30:
            return {"status": "error", "message": f"Insufficient data: {len(df)} games"}
        
        # Prepare features
        X = df[self.feature_names].fillna(0)
        y = df[self.config.TARGET]
        
        # Split
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42
        )
        
        # Train Logistic Regression
        lr_model = LogisticRegression(
            random_state=42,
            max_iter=500,
            C=0.1
        )
        lr_model.fit(X_train, y_train)
        
        # Train XGBoost
        xgb_model = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            random_state=42,
            use_label_encoder=False,
            eval_metric="logloss"
        )
        xgb_model.fit(X_train, y_train)
        
        # Evaluate
        lr_pred = lr_model.predict(X_test)
        lr_prob = lr_model.predict_proba(X_test)[:, 1]
        lr_acc = accuracy_score(y_test, lr_pred)
        lr_auc = roc_auc_score(y_test, lr_prob)
        lr_brier = brier_score_loss(y_test, lr_prob)
        
        xgb_pred = xgb_model.predict(X_test)
        xgb_prob = xgb_model.predict_proba(X_test)[:, 1]
        xgb_acc = accuracy_score(y_test, xgb_pred)
        xgb_auc = roc_auc_score(y_test, xgb_prob)
        xgb_brier = brier_score_loss(y_test, xgb_prob)
        
        self.models["logistic"] = lr_model
        self.models["xgboost"] = xgb_model
        self.is_trained = True
        
        # Feature importance (XGBoost)
        importance = pd.DataFrame({
            "feature": self.feature_names,
            "importance": xgb_model.feature_importances_
        }).sort_values("importance", ascending=False)
        
        metrics = {
            "status": "trained",
            "n_games": len(df),
            "logistic_regression": {
                "accuracy": lr_acc,
                "auc": lr_auc,
                "brier": lr_brier
            },
            "xgboost": {
                "accuracy": xgb_acc,
                "auc": xgb_auc,
                "brier": xgb_brier
            },
            "feature_importance": importance.head(10).to_dict()
        }
        
        logger.info(f"Trained on {len(df)} games. LR AUC: {lr_auc:.3f}, XGB AUC: {xgb_auc:.3f}")
        
        # Fit calibration if we have enough data with odds
        self._fit_calibrator(df, X, y)
        
        return metrics
    
    def _fit_calibrator(self, df: pd.DataFrame, X: pd.DataFrame, y: pd.Series):
        """Fit EV calibrator if we have odds data"""
        if "home_implied_prob" not in df.columns:
            return
        
        mask = df["home_implied_prob"].notna() & (df["home_implied_prob"] > 0) & (df["home_implied_prob"] < 1)
        if mask.sum() < 50:
            logger.warning(f"Insufficient odds data for calibration: {mask.sum()} games")
            return
        
        X_calib = X[mask]
        y_calib = y[mask]
        
        # Get model probabilities
        model_probs = self.models["xgboost"].predict_proba(X_calib)[:, 1]
        
        # Fit calibrator
        self.calibrator = EVCalibrator()
        self.calibrator.fit(y_calib.values, model_probs)
        
        logger.info(f"Fitted calibrator on {len(y_calib)} games")
    
    def predict(
        self,
        game: Dict,
        team_stats: Dict,
        standings: List[Dict],
        odds: Optional[Dict] = None,
        injuries: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Predict game outcome"""
        
        if not self.is_trained:
            return {"status": "error", "message": "Model not trained"}
        
        engine = NBAFeatureEngine()
        
        home_team_id = game.get("home_team", {}).get("id")
        away_team_id = game.get("away_team", {}).get("id")
        
        home_stats = team_stats.get(home_team_id, {})
        away_stats = team_stats.get(away_team_id, {})
        
        game_date = datetime.fromisoformat(game.get("start_time", datetime.now().isoformat()))
        
        features = engine.generate_all_features(
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            home_stats=home_stats,
            away_stats=away_stats,
            standings=standings,
            home_odds=odds.get("moneyline", {}).get("home") if odds else None,
            away_odds=odds.get("moneyline", {}).get("away") if odds else None,
            home_missing=injuries.get(home_team_id, []) if injuries else [],
            away_missing=injuries.get(away_team_id, []) if injuries else [],
            game_date=game_date
        )
        
        X = pd.DataFrame([features])[self.feature_names].fillna(0)
        
        # Ensemble prediction
        lr_prob = self.models["logistic"].predict_proba(X)[0, 1]
        xgb_prob = self.models["xgboost"].predict_proba(X)[0, 1]
        
        raw_prob = 0.3 * lr_prob + 0.7 * xgb_prob
        
        # Apply calibration if available
        if self.calibrator is not None:
            calibrated_prob = self.calibrator.get_calibrated_prob(raw_prob)
        else:
            calibrated_prob = raw_prob
        
        # Calculate edge from odds
        home_implied = None
        if odds and odds.get("moneyline", {}).get("home"):
            home_implied = 1 / odds["moneyline"]["home"]
            edge = calibrated_prob - home_implied
            ev = calibrated_prob * (odds["moneyline"]["home"] - 1) - (1 - calibrated_prob)
        else:
            edge = 0
            ev = 0
        
        decision = "no_bet"
        if edge >= self.config.MIN_EDGE:
            if calibrated_prob >= 0.5:
                decision = "bet_home"
            else:
                decision = "bet_away"
        
        return {
            "status": "ok",
            "home_win_prob": calibrated_prob,
            "away_win_prob": 1 - calibrated_prob,
            "raw_prob": raw_prob,
            "calibrated": self.calibrator is not None,
            "logistic_prob": lr_prob,
            "xgboost_prob": xgb_prob,
            "edge": edge,
            "expected_value": ev,
            "decision": decision,
            "confidence": "high" if abs(calibrated_prob - 0.5) > 0.15 else "medium"
        }
    
    def predict_proba(
        self,
        X: pd.DataFrame
    ) -> np.ndarray:
        """Predict probabilities for multiple games"""
        
        if not self.is_trained:
            return np.zeros(len(X))
        
        X = X[self.feature_names].fillna(0)
        
        lr_prob = self.models["logistic"].predict_proba(X)[:, 1]
        xgb_prob = self.models["xgboost"].predict_proba(X)[:, 1]
        
        return 0.3 * lr_prob + 0.7 * xgb_prob


class NBAEVEngine:
    """Calculate EV for NBA bets"""
    
    def __init__(self, model: NBAModelTrainer, config = None):
        self.model = model
        self.config = config or NBAModelConfig()
    
    def calculate_ev(
        self,
        probability: float,
        odds: float,
        threshold: float = None
    ) -> Dict[str, Any]:
        """Calculate expected value for a bet"""
        
        threshold = threshold or self.config.DEFAULT_THRESHOLD
        
        implied = 1 / odds if odds > 0 else 0.5
        edge = probability - implied
        
        ev = probability * (odds - 1) - (1 - probability)
        
        # Kelly fraction (simplified)
        b = odds - 1
        p = probability
        q = 1 - p
        
        kelly = 0
        if b > 0:
            kelly = (b * p - q) / b
            kelly = max(0, kelly * 0.25)  # Half-Kelly
        
        # Decision
        if probability < threshold:
            decision = "no_bet"
            reason = f"Probability {probability:.2%} below threshold {threshold:.2%}"
        elif edge < self.config.MIN_EDGE:
            decision = "no_bet"
            reason = f"Edge {edge:.2%} below minimum {self.config.MIN_EDGE:.2%}"
        else:
            decision = "bet"
            reason = f"Positive edge: {edge:.2%}, EV: {ev:.2%}"
        
        return {
            "probability": probability,
            "implied_probability": implied,
            "odds": odds,
            "edge": edge,
            "expected_value": ev,
            "kelly_fraction": kelly,
            "decision": decision,
            "reason": reason
        }


def train_nba_model(
    games: List[Dict],
    team_stats: Dict,
    standings: List[Dict],
    odds_data: Optional[Dict] = None,
    injuries: Optional[Dict] = None
) -> Tuple[NBAModelTrainer, Dict]:
    """Convenience function to train NBA model"""
    
    trainer = NBAModelTrainer()
    metrics = trainer.train(games, team_stats, standings, odds_data, injuries)
    
    return trainer, metrics


if __name__ == "__main__":
    print("=== Testing NBA Model Training ===")
    print("\n[NBA Model Ready for Training]")
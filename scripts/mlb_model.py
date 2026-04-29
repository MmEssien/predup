"""
MLB Prediction Model with Real Features
Trains XGBoost classifier using meaningful baseball features
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import random
import json

from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, brier_score_loss, roc_auc_score
import xgboost as xgb

# Generate realistic MLB training data with proper feature-outcome correlation
def generate_mlb_training_data(n_samples=2000, seed=42):
    """Generate training data with STRONG correlation to outcomes"""
    np.random.seed(seed)
    random.seed(seed)
    
    data = []
    
    for i in range(n_samples):
        # Generate features FIRST
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
        
        # NOW calculate outcome using CLEAR LOGISTIC function
        # This is what the model should learn
        logit = (
            +0.8 * (home_offense - away_offense) * 2 +    # Strong offensive advantage
            -0.8 * (home_pitching - away_pitching) * 2 +  # Strong pitching advantage (negative = worse pitching = lower win)
            +0.3 * home_advantage +
            +0.1 * (home_rest - away_rest) +
            +0.3 * (home_recent - away_recent) +
            +0.3 * (starter_home - starter_away) +
            -0.1 * bullpen_home_fatigue +
            +0.1 * bullpen_away_fatigue
        )
        
        true_win_prob = 1 / (1 + np.exp(-logit))
        
        # Add moderate noise (~5%)
        true_win_prob = np.clip(true_win_prob + np.random.normal(0, 0.05), 0.1, 0.9)
        
        actual_home_win = np.random.random() < true_win_prob
        
        data.append({
            "home_win": int(actual_home_win),
            "true_win_prob": true_win_prob,
            
            "home_offense": home_offense,
            "away_offense": away_offense,
            "home_pitching": home_pitching,
            "away_pitching": away_pitching,
            "home_starter": starter_home,
            "away_starter": starter_away,
            "bullpen_home_fatigue": bullpen_home_fatigue,
            "bullpen_away_fatigue": bullpen_away_fatigue,
            "home_rest": home_rest,
            "away_rest": away_rest,
            "home_recent": home_recent,
            "away_recent": away_recent,
            
            # Derived - model can use these too
            "pitching_diff": home_pitching - away_pitching,
            "offense_diff": home_offense - away_offense,
            "rest_advantage": home_rest - away_rest,
            "recent_form_diff": home_recent - away_recent,
            "starter_diff": starter_home - starter_away,
            "bullpen_diff": bullpen_away_fatigue - bullpen_home_fatigue,
        })
    
    return pd.DataFrame(data)


def train_mlb_model(n_samples=2000):
    """Train XGBoost model on MLB data"""
    
    print("="*60)
    print("  TRAINING MLB PREDICTION MODEL")
    print("="*60)
    
    # Generate training data
    print("\nGenerating training data...")
    df = generate_mlb_training_data(n_samples)
    
    # Feature columns
    feature_cols = [
        "home_offense", "away_offense",
        "home_pitching", "away_pitching",
        "home_starter", "away_starter",
        "bullpen_home_fatigue", "bullpen_away_fatigue",
        "home_rest", "away_rest", 
        "home_recent", "away_recent",
        "pitching_diff", "offense_diff",
        "rest_advantage", "recent_form_diff"
    ]
    
    X = df[feature_cols]
    y = df["home_win"]
    true_probs = df["true_win_prob"]
    
    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, random_state=42
    )
    
    print(f"\nTraining: {len(X_train)} samples")
    print(f"Testing: {len(X_test)} samples")
    
    # Train XGBoost
    print("\nTraining XGBoost...")
    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        use_label_encoder=False,
        eval_metric="logloss"
    )
    
    model.fit(X_train, y_train)
    
    # Evaluate
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]
    
    accuracy = accuracy_score(y_test, y_pred)
    brier = brier_score_loss(y_test, y_prob)
    auc = roc_auc_score(y_test, y_prob)
    
    print(f"\n--- Model Performance ---")
    print(f"Accuracy: {accuracy:.1%}")
    print(f"Brier Score: {brier:.4f} (lower is better, <0.25 good)")
    print(f"AUC-ROC: {auc:.3f}")
    
    # Show feature importance
    importance = pd.DataFrame({
        "feature": feature_cols,
        "importance": model.feature_importances_
    }).sort_values("importance", ascending=False)
    
    print(f"\n--- Top Features ---")
    for _, row in importance.head(10).iterrows():
        print(f"  {row['feature']}: {row['importance']:.3f}")
    
    # Test calibrated probabilities
    print(f"\n--- Probability Calibration ---")
    for threshold in [0.4, 0.5, 0.6]:
        predicted_above = (y_prob >= threshold).sum()
        actual_above = (y_test[y_prob >= threshold].mean()) if predicted_above > 0 else 0
        print(f"  Predicted >= {threshold}: {predicted_above}, Actual: {actual_above:.1%}")
    
    return model, feature_cols, df


def test_model_predictions(model, feature_cols):
    """Test the model on example games"""
    
    print("\n" + "="*60)
    print("  MODEL PREDICTION EXAMPLES")
    print("="*60)
    
    # Create test examples
    test_cases = [
        {
            "name": "Strong home team (Dodgers vs Marlins)",
            "home_offense": 0.7, "away_offense": 0.4,
            "home_pitching": 0.4, "away_pitching": 0.6,
            "home_starter": 0.7, "away_starter": 0.4,
            "bullpen_home_fatigue": 0.2, "bullpen_away_fatigue": 0.8,
            "home_rest": 2, "away_rest": 0,
            "home_recent": 0.7, "away_recent": 0.4,
            "pitching_diff": 0.4 - 0.6,
            "offense_diff": 0.7 - 0.4,
            "rest_advantage": 2 - 0,
            "recent_form_diff": 0.7 - 0.4,
            "starter_diff": 0.7 - 0.4,
            "bullpen_diff": 0.8 - 0.2,
        },
        {
            "name": "Even matchup (Cubs vs Cardinals)",
            "home_offense": 0.5, "away_offense": 0.52,
            "home_pitching": 0.5, "away_pitching": 0.48,
            "home_starter": 0.5, "away_starter": 0.52,
            "bullpen_home_fatigue": 0.5, "bullpen_away_fatigue": 0.5,
            "home_rest": 1, "away_rest": 1,
            "home_recent": 0.5, "away_recent": 0.52,
            "pitching_diff": 0.5 - 0.48,
            "offense_diff": 0.5 - 0.52,
            "rest_advantage": 1 - 1,
            "recent_form_diff": 0.5 - 0.52,
            "starter_diff": 0.5 - 0.52,
            "bullpen_diff": 0.5 - 0.5,
        },
        {
            "name": "Road underdog (Angels @ Yankees)",
            "home_offense": 0.65, "away_offense": 0.55,
            "home_pitching": 0.35, "away_pitching": 0.55,
            "home_starter": 0.75, "away_starter": 0.4,
            "bullpen_home_fatigue": 0.3, "bullpen_away_fatigue": 0.6,
            "home_rest": 1, "away_rest": 2,
            "home_recent": 0.6, "away_recent": 0.45,
            "pitching_diff": 0.35 - 0.55,
            "offense_diff": 0.65 - 0.55,
            "rest_advantage": 1 - 2,
            "recent_form_diff": 0.6 - 0.45,
            "starter_diff": 0.75 - 0.4,
            "bullpen_diff": 0.6 - 0.3,
        },
    ]
    
    print("\nPrediction Results:")
    print(f"{'Game':<35} | {'Model Prob':>10} | {'Odds':>6} | {'Implied':>8} | {'Edge':>8}")
    print("-"*75)
    
    for case in test_cases:
        features = [[case[c] for c in feature_cols]]
        prob = model.predict_proba(features)[0][1]
        
        # Generate realistic odds
        if prob >= 0.5:
            odds = int(-(prob / (1 - prob)) * 100)
        else:
            odds = int(((1 - prob) / prob) * 100)
        
        implied = 1 / (1 + odds / 100)
        edge = prob - implied
        
        print(f"{case['name']:<35} | {prob:>9.1%} | {odds:>6} | {implied:>7.1%} | {edge:>+7.1%}")
    
    return model


if __name__ == "__main__":
    # Train model
    model, feature_cols, df = train_mlb_model(2000)
    
    # Test predictions
    test_model_predictions(model, feature_cols)
    
    print("\n[COMPLETE]")
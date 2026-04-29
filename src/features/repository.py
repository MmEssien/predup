"""Feature repository for storage and retrieval"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
import pandas as pd
import numpy as np

from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, asc

from src.data.database import Fixture
from src.features.engineer import FeatureEngineer

logger = logging.getLogger(__name__)


class FeatureRepository:
    def __init__(self, session: Session, config: Optional[Dict] = None):
        self.session = session
        self.config = config or {}
        self.engineer = FeatureEngineer(session, config)

    def generate_and_store_features(
        self,
        fixture_id: int,
        include_targets: bool = True
    ) -> Dict[str, Any]:
        """Generate and return features for a fixture"""
        return self.engineer.generate_features_for_fixture(
            fixture_id,
            include_targets=include_targets
        )

    def get_feature_vector(
        self,
        fixture_id: int,
        feature_names: Optional[List[str]] = None
    ) -> np.ndarray:
        """Get feature vector for prediction"""
        features = self.generate_and_store_features(fixture_id, include_targets=False)

        if feature_names is None:
            feature_names = self._get_default_features()

        vector = []
        for name in feature_names:
            vector.append(features.get(name, 0))

        return np.array(vector)

    def _get_default_features(self) -> List[str]:
        """Get default feature list - including Phase 2 enhancements"""
        return [
            # Form features
            "home_form_5_points", "home_form_5_wins", "home_form_5_draws", "home_form_5_losses",
            "home_form_5_gf", "home_form_5_ga",
            "home_form_10_points", "home_form_10_wins", "home_form_10_draws", "home_form_10_losses",
            "home_form_10_gf", "home_form_10_ga",
            "away_form_5_points", "away_form_5_wins", "away_form_5_draws", "away_form_5_losses",
            "away_form_5_gf", "away_form_5_ga",
            "away_form_10_points", "away_form_10_wins", "away_form_10_draws", "away_form_10_losses",
            "away_form_10_gf", "away_form_10_ga",
            "form_diff_5", "form_diff_10",
            
            # H2H features
            "h2h_matches", "h2h_home_wins", "h2h_away_wins", "h2h_draws",
            "h2h_home_goals", "h2h_away_goals",
            
            # Venue features
            "home_venue_matches", "home_venue_wins", "home_venue_draws", "home_venue_losses",
            "home_venue_gf", "home_venue_ga",
            
            # Weather features (Phase 2)
            "weather_temp_max", "weather_temp_min", "weather_precip_prob",
            "weather_wind_speed", "weather_impact",
            
            # Odds features (Phase 2)  
            "odds_home_implied", "odds_away_implied", "odds_draw_implied",
            "market_overround", "fair_home_prob", "fair_away_prob",
            
            # Rest and situational (Phase 2)
            "home_rest_days", "away_rest_days", "rest_diff",
            
            # Advanced form features (Phase 2)
            "home_win_streak", "away_win_streak",
            "home_clean_sheet_pct", "away_clean_sheet_pct",
            "home_goals_per_game", "away_goals_per_game",
            "home_btts_frequency", "away_btts_frequency",
            "home_overs_frequency", "away_overs_frequency",
            "goals_per_game_diff", "clean_sheet_diff",
            
            # Basic situational
            "day_of_week", "hour", "is_weekend", "matchday", "season",
        ]

    def get_training_data(
        self,
        competition_id: Optional[int] = None,
        min_date: Optional[datetime] = None,
        max_date: Optional[datetime] = None,
        target_column: str = "target_over_25"
    ) -> tuple:
        """Get training data (X, y)"""
        df = self.engineer.generate_dataset(
            competition_id=competition_id,
            min_date=min_date,
            max_date=max_date
        )

        df = df.dropna(subset=[target_column])

        feature_names = [col for col in df.columns if col.startswith(("home_", "away_", "h2h", "form_", "venue_", "day_", "hour", "is_", "matchday", "season"))]
        feature_names = [col for col in feature_names if col not in ["home_team_id", "away_team_id"]]

        X = df[feature_names].fillna(0)
        y = df[target_column]

        return X, y

    def get_upcoming_features(
        self,
        days_ahead: int = 7
    ) -> pd.DataFrame:
        """Get features for upcoming fixtures"""
        from datetime import timedelta

        end_date = datetime.utcnow() + timedelta(days=days_ahead)

        fixtures = self.session.query(Fixture).filter(
            and_(
                Fixture.status == "SCHEDULED",
                Fixture.utc_date <= end_date,
                Fixture.utc_date >= datetime.utcnow()
            )
        ).order_by(Fixture.utc_date).all()

        records = []
        for fixture in fixtures:
            try:
                features = self.generate_and_store_features(
                    fixture.id,
                    include_targets=False
                )
                records.append(features)
            except Exception as e:
                logger.warning(f"Error for fixture {fixture.id}: {e}")

        return pd.DataFrame(records)

    def get_feature_importance(
        self,
        competition_id: Optional[int] = None,
        n_estimators: int = 100
    ) -> pd.DataFrame:
        """Calculate feature importance using XGBoost"""
        try:
            from xgboost import XGBClassifier
            from sklearn.model_selection import train_test_split

            X, y = self.get_training_data(
                competition_id=competition_id,
                target_column="target_over_25"
            )

            if len(X) < 50:
                return pd.DataFrame()

            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42
            )

            model = XGBClassifier(
                n_estimators=n_estimators,
                max_depth=5,
                learning_rate=0.1,
                random_state=42
            )
            model.fit(X_train, y_train)

            importance = pd.DataFrame({
                "feature": X.columns,
                "importance": model.feature_importances_
            }).sort_values("importance", ascending=False)

            return importance

        except Exception as e:
            logger.error(f"Error calculating feature importance: {e}")
            return pd.DataFrame()

    def validate_features(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Validate feature quality"""
        report = {
            "total_features": len(df.columns),
            "null_counts": {},
            "zero_variance": [],
            "high_correlation_pairs": [],
        }

        for col in df.columns:
            null_count = df[col].isnull().sum()
            if null_count > 0:
                report["null_counts"][col] = null_count

            if df[col].nunique() <= 1:
                report["zero_variance"].append(col)

        numeric_cols = df.select_dtypes(include=[np.number]).columns
        if len(numeric_cols) > 1:
            corr_matrix = df[numeric_cols].corr()
            for i in range(len(corr_matrix.columns)):
                for j in range(i + 1, len(corr_matrix.columns)):
                    if abs(corr_matrix.iloc[i, j]) > 0.95:
                        report["high_correlation_pairs"].append((
                            corr_matrix.columns[i],
                            corr_matrix.columns[j],
                            corr_matrix.iloc[i, j]
                        ))

        return report
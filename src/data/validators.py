"""Data validators for PredUp"""

import pandas as pd
import logging

logger = logging.getLogger(__name__)


class DataValidator:
    """Validate data quality"""

    @staticmethod
    def validate_matches(df: pd.DataFrame) -> bool:
        required_columns = [
            "match_id", "date", "home_team_id", "away_team_id",
            "home_score", "away_score"
        ]

        for col in required_columns:
            if col not in df.columns:
                logger.error(f"Missing required column: {col}")
                return False

        if df.empty:
            logger.error("DataFrame is empty")
            return False

        null_counts = df[required_columns].isnull().sum()
        if null_counts.any():
            logger.warning(f"Null values found: {null_counts[null_counts > 0].to_dict()}")

        return True

    @staticmethod
    def validate_team(df: pd.DataFrame) -> bool:
        required = ["team_id", "team_name"]
        for col in required:
            if col not in df.columns:
                logger.error(f"Missing required column: {col}")
                return False
        return True

    @staticmethod
    def validate_scores(df: pd.DataFrame) -> bool:
        if "home_score" in df.columns and "away_score" in df.columns:
            valid_scores = (
                df["home_score"].notna() &
                df["away_score"].notna() &
                (df["home_score"] >= 0) &
                (df["away_score"] >= 0)
            )
            invalid = ~valid_scores.sum()
            if invalid > 0:
                logger.warning(f"Found {invalid} invalid score entries")
        return True
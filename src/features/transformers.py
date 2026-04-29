"""Feature transformers for PredUp"""

import logging
from typing import List, Optional, Dict, Any, Tuple
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler, LabelEncoder, OneHotEncoder
from sklearn.base import BaseEstimator, TransformerMixin

logger = logging.getLogger(__name__)


class CategoricalEncoder(BaseEstimator, TransformerMixin):
    def __init__(self, columns: Optional[List[str]] = None, method: str = "label"):
        self.columns = columns or []
        self.method = method
        self.encoders: Dict[str, LabelEncoder] = {}
        self.onehot: Optional[OneHotEncoder] = None

    def fit(self, X: pd.DataFrame, y=None):
        X = X.copy()

        if self.method == "label":
            for col in self.columns:
                if col in X.columns:
                    le = LabelEncoder()
                    le.fit(X[col].astype(str).fillna("unknown"))
                    self.encoders[col] = le
        elif self.method == "onehot":
            self.onehot = OneHotEncoder(
                sparse_output=False,
                handle_unknown="ignore"
            )
            self.onehot.fit(X[self.columns])

        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        X = X.copy()

        if self.method == "label":
            for col, encoder in self.encoders.items():
                if col in X.columns:
                    X[col] = X[col].astype(str).fillna("unknown")
                    X[col] = encoder.transform(X[col])
        elif self.method == "onehot" and self.onehot:
            encoded = self.onehot.transform(X[self.columns])
            feature_names = self.onehot.get_feature_names_out(self.columns)
            for i, name in enumerate(feature_names):
                X[name] = encoded[:, i]
            X = X.drop(columns=self.columns)

        return X

    def fit_transform(self, X: pd.DataFrame, y=None):
        return self.fit(X, y).transform(X)


class NumericImputer(BaseEstimator, TransformerMixin):
    def __init__(self, columns: Optional[List[str]] = None, strategy: str = "median"):
        self.columns = columns or []
        self.strategy = strategy
        self.values: Dict[str, float] = {}

    def fit(self, X: pd.DataFrame, y=None):
        X = X.copy()

        for col in self.columns:
            if col in X.columns:
                if self.strategy == "median":
                    self.values[col] = X[col].median()
                elif self.strategy == "mean":
                    self.values[col] = X[col].mean()
                elif self.strategy == "zero":
                    self.values[col] = 0

        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        X = X.copy()

        for col, value in self.values.items():
            if col in X.columns:
                X[col] = X[col].fillna(value)

        return X

    def fit_transform(self, X: pd.DataFrame, y=None):
        return self.fit(X, y).transform(X)


class FeatureSelector(BaseEstimator, TransformerMixin):
    def __init__(self, features: Optional[List[str]] = None, exclude: Optional[List[str]] = None):
        self.features = features or []
        self.exclude = exclude or []

    def fit(self, X: pd.DataFrame, y=None):
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        X = X.copy()

        if self.features:
            X = X[self.features]
        elif self.exclude:
            X = X.drop(columns=[c for c in self.exclude if c in X.columns])

        return X


class TargetEncoder(BaseEstimator, TransformerMixin):
    def __init__(self, columns: Optional[List[str]] = None, smoothing: float = 1.0):
        self.columns = columns or []
        self.smoothing = smoothing
        self.means: Dict[str, Dict[Any, float]] = {}
        self.global_mean: float = 0.0

    def fit(self, X: pd.DataFrame, y: pd.Series):
        X = X.copy()
        self.global_mean = y.mean() if y is not None else 0.0

        for col in self.columns:
            if col not in X.columns:
                continue

            means = {}
            for val in X[col].unique():
                mask = X[col] == val
                count = mask.sum()
                mean = y[mask].mean() if y is not None else self.global_mean
                smoothed = (count * mean + self.smoothing * self.global_mean) / (count + self.smoothing)
                means[val] = smoothed

            self.means[col] = means

        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        X = X.copy()

        for col, means in self.means.items():
            if col in X.columns:
                X[col] = X[col].map(means).fillna(self.global_mean)

        return X


class FeatureClipper(BaseEstimator, TransformerMixin):
    def __init__(self, columns: Optional[List[str]] = None, lower: float = None, upper: float = None):
        self.columns = columns or []
        self.lower = lower
        self.upper = upper

    def fit(self, X: pd.DataFrame, y=None):
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        X = X.copy()

        for col in self.columns:
            if col in X.columns:
                if self.lower is not None:
                    X[col] = X[col].clip(lower=self.lower)
                if self.upper is not None:
                    X[col] = X[col].clip(upper=self.upper)

        return X


class LogTransformer(BaseEstimator, TransformerMixin):
    def __init__(self, columns: Optional[List[str]] = None, add_constant: float = 1.0):
        self.columns = columns or []
        self.add_constant = add_constant

    def fit(self, X: pd.DataFrame, y=None):
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        X = X.copy()

        for col in self.columns:
            if col in X.columns:
                X[col] = np.log1p(X[col].clip(lower=0) + self.add_constant)

        return X


class FeatureDifferencer(BaseEstimator, TransformerMixin):
    def __init__(self, pairs: Optional[List[Tuple[str, str]]] = None):
        self.pairs = pairs or []

    def fit(self, X: pd.DataFrame, y=None):
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        X = X.copy()

        for col1, col2 in self.pairs:
            if col1 in X.columns and col2 in X.columns:
                new_col = f"{col1}_diff_{col2}"
                X[new_col] = X[col1] - X[col2]

        return X


class InteractionCreator(BaseEstimator, TransformerMixin):
    def __init__(self, pairs: Optional[List[Tuple[str, str]]] = None, operations: Optional[List[str]] = None):
        self.pairs = pairs or []
        self.operations = operations or ["multiply", "ratio"]

    def fit(self, X: pd.DataFrame, y=None):
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        X = X.copy()

        for col1, col2 in self.pairs:
            if col1 not in X.columns or col2 not in X.columns:
                continue

            if "multiply" in self.operations:
                X[f"{col1}_x_{col2}"] = X[col1] * X[col2]

            if "ratio" in self.operations:
                X[f"{col1}_div_{col2}"] = X[col1] / (X[col2] + 1e-6)

            if "add" in self.operations:
                X[f"{col1}_plus_{col2}"] = X[col1] + X[col2]

            if "subtract" in self.operations:
                X[f"{col1}_minus_{col2}"] = X[col1] - X[col2]

        return X


class Pipeline:
    def __init__(self, steps: List[Tuple[str, Any]]):
        self.steps = steps

    def fit(self, X: pd.DataFrame, y=None):
        for name, transformer in self.steps:
            if hasattr(transformer, "fit"):
                if y is not None and hasattr(transformer, "fit_transform"):
                    X = transformer.fit_transform(X, y)
                else:
                    X = transformer.fit(X, y)
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        for name, transformer in self.steps:
            if hasattr(transformer, "transform"):
                X = transformer.transform(X)
        return X

    def fit_transform(self, X: pd.DataFrame, y=None):
        return self.fit(X, y).transform(X)


def create_feature_pipeline(config: Optional[Dict] = None) -> Pipeline:
    config = config or {}

    steps = [
        ("imputer", NumericImputer(
            strategy=config.get("impute_strategy", "median")
        )),
        ("clipper", FeatureClipper(
            lower=config.get("clip_lower"),
            upper=config.get("clip_upper")
        )),
        ("scaler", StandardScaler()),
    ]

    return Pipeline(steps)
"""Pydantic schemas for PredUp API"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class TeamBase(BaseModel):
    external_id: int
    name: str
    short_name: Optional[str] = None
    tla: Optional[str] = None
    venue: Optional[str] = None


class TeamResponse(TeamBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class FixtureBase(BaseModel):
    external_id: int
    home_team_id: int
    away_team_id: int
    utc_date: datetime


class FixtureResponse(FixtureBase):
    id: int
    competition_id: Optional[int] = None
    season: int
    status: str
    home_score: Optional[int] = None
    away_score: Optional[int] = None

    class Config:
        from_attributes = True


class PredictionRequest(BaseModel):
    fixture_id: int
    prediction_type: str = Field(default="over_25", description="Type of prediction")
    confidence_threshold: float = Field(default=0.75, ge=0.5, le=1.0)


class PredictionResponse(BaseModel):
    fixture_id: int
    predicted_value: Any
    probability: float
    confidence: float
    is_accepted: bool
    model_predictions: Dict[str, float]


class BatchPredictionRequest(BaseModel):
    fixture_ids: List[int]
    prediction_type: str = "over_25"
    confidence_threshold: float = Field(default=0.75, ge=0.5, le=1.0)


class BatchPredictionResponse(BaseModel):
    predictions: List[PredictionResponse]
    total: int
    accepted: int
    rejected: int


class ModelMetrics(BaseModel):
    accuracy: float
    precision: float
    recall: float
    f1: float
    roc_auc: Optional[float] = None


class ModelInfo(BaseModel):
    model_name: str
    version: str
    is_active: bool
    metrics: ModelMetrics
    registered_at: datetime


class UpcomingMatch(BaseModel):
    fixture_id: int
    external_id: int
    competition: Optional[str] = None
    date: datetime
    home_team: str
    away_team: str
    venue: Optional[str] = None


class FeatureImportance(BaseModel):
    feature: str
    importance: float


class TrainingRequest(BaseModel):
    target_column: str = "target_over_25"
    competition_id: Optional[int] = None
    test_size: float = Field(default=0.3, ge=0.1, le=0.5)


class TrainingResponse(BaseModel):
    model_name: str
    version: str
    metrics: ModelMetrics
    feature_importance: List[FeatureImportance]


class HealthResponse(BaseModel):
    status: str
    service: str
    database: str = "connected"
    models_loaded: int


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None


class ValidationRequest(BaseModel):
    fixture_id: int
    predicted_value: Any
    actual_value: Any


class ValidationResponse(BaseModel):
    prediction_id: int
    is_correct: bool
    settled_at: datetime


class InjuryInfo(BaseModel):
    player_id: int
    name: str
    position: str
    type: str
    severity: float
    is_key_player: bool = False


class LineupRequest(BaseModel):
    fixture_id: int
    home_team_id: int
    away_team_id: int
    match_date: datetime
    injuries: Optional[List[InjuryInfo]] = None


class LineupResponse(BaseModel):
    fixture_id: int
    home_adjustment: float = 0.0
    away_adjustment: float = 0.0
    key_absences: List[str] = []
    confidence_reduction: float = 0.0
    data_freshness: str = "unknown"


class SettlementResponse(BaseModel):
    predictions_settled: int
    total_profit: float
    win_rate: float
    roi: float
    settled_at: datetime


class HealthReportResponse(BaseModel):
    report_date: datetime
    total_bets: int
    total_roi: float
    bl1_roi: float = 0.0
    bl1_bets: int = 0
    pl_roi: float = 0.0
    pl_bets: int = 0
    calibration_ece: float = 0.0
    calibration_drift: float = 0.0
    max_drawdown_pct: float = 0.0
    recommendation: str = "CONTINUE"
    recommendation_reason: str = ""
    recent_reports: List[Dict[str, Any]] = []


class DashboardStats(BaseModel):
    total_fixtures_today: int
    positive_ev_opportunities: int
    sports_active: List[str]
    projected_edge_today: float
    yesterday_roi: float
    open_predictions: int
    last_updated: str


class LivePrediction(BaseModel):
    fixture_id: int
    sport: str
    league: str
    home_team: str
    away_team: str
    start_time: str
    home_odds: float
    away_odds: float
    model_probability: float
    implied_prob: float
    ev_percent: float
    kelly_percent: float
    recommended_side: str
    confidence_score: str
    odds_source: str


class HistoricalPick(BaseModel):
    fixture_id: int
    sport: str
    league: str
    predicted_value: str
    probability: float
    confidence: str
    is_accepted: bool
    ev: Optional[float] = None
    kelly_pct: Optional[float] = None
    odds_taken: Optional[float] = None
    closing_odds: Optional[float] = None
    result: Optional[str] = None
    profit: Optional[float] = None
    clv: Optional[float] = None
    clv_percent: Optional[float] = None
    created_at: Optional[str] = None
    settled_at: Optional[str] = None
    fixture: Optional[Dict[str, Any]] = None


class PerformanceMetrics(BaseModel):
    total_bets: int
    win_rate: float
    total_roi: float
    avg_clv: float
    roi_over_time: List[Dict[str, Any]]
    win_rate_by_sport: List[Dict[str, Any]]
    profit_by_month: List[Dict[str, Any]]


class FixtureDetail(BaseModel):
    fixture: Dict[str, Any]
    odds: Dict[str, Any]
    prediction: Dict[str, Any]
    edge_explanation: str
    kelly_stake: float
    recent_form: Dict[str, Any]
    injuries: List[Dict[str, Any]]
    lineup_status: Dict[str, str]
    confidence_score: int
    market_movement: List[Dict[str, Any]]


class SettingsResponse(BaseModel):
    enabled_sports: List[str]
    ev_threshold: float
    kelly_multiplier: float
    auto_refresh_interval: int
    api_health: Dict[str, Any]
    odds_source_priority: List[str]
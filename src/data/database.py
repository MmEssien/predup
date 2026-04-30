"""Database models for PredUp"""

from datetime import datetime, date, date

from sqlalchemy import (
    Column, Integer, String, Date, DateTime, ForeignKey,
    Boolean, Float, Text, Index, UniqueConstraint, JSON
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True)
    external_id = Column(Integer, unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    short_name = Column(String(50))
    tla = Column(String(10))
    crest_url = Column(String(500))
    venue = Column(String(255))
    league = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    home_fixtures = relationship(
        "Fixture", foreign_keys="Fixture.home_team_id", back_populates="home_team"
    )
    away_fixtures = relationship(
        "Fixture", foreign_keys="Fixture.away_team_id", back_populates="away_team"
    )
    players = relationship("Player", back_populates="team")


class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True)
    external_id = Column(Integer, unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    position = Column(String(50))
    date_of_birth = Column(DateTime)
    nationality = Column(String(100))
    team_id = Column(Integer, ForeignKey("teams.id"), index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    team = relationship("Team", back_populates="players")
    appearances = relationship("PlayerAppearance", back_populates="player")


class Competition(Base):
    __tablename__ = "competitions"

    id = Column(Integer, primary_key=True)
    external_id = Column(Integer, unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    code = Column(String(20), nullable=False, index=True)
    area_name = Column(String(100))
    emblem_url = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)

    fixtures = relationship("Fixture", back_populates="competition")


class Fixture(Base):
    __tablename__ = "fixtures"

    id = Column(Integer, primary_key=True)
    external_id = Column(Integer, unique=True, nullable=False, index=True)
    competition_id = Column(Integer, ForeignKey("competitions.id"), index=True)
    season = Column(Integer, nullable=False)
    matchday = Column(Integer)
    utc_date = Column(DateTime, nullable=False, index=True)
    status = Column(String(50), nullable=False, default="SCHEDULED")
    home_team_id = Column(Integer, ForeignKey("teams.id"), index=True)
    away_team_id = Column(Integer, ForeignKey("teams.id"), index=True)
    home_score = Column(Integer)
    away_score = Column(Integer)
    winner = Column(String(50))
    venue = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    competition = relationship("Competition", back_populates="fixtures")
    home_team = relationship(
        "Team", foreign_keys=[home_team_id], back_populates="home_fixtures"
    )
    away_team = relationship(
        "Team", foreign_keys=[away_team_id], back_populates="away_fixtures"
    )
    events = relationship("FixtureEvent", back_populates="fixture")
    appearances = relationship("PlayerAppearance", back_populates="fixture")

    __table_args__ = (
        Index("ix_fixture_teams", "home_team_id", "away_team_id"),
        Index("ix_fixture_date_status", "utc_date", "status"),
    )


class FixtureEvent(Base):
    __tablename__ = "fixture_events"

    id = Column(Integer, primary_key=True)
    fixture_id = Column(Integer, ForeignKey("fixtures.id"), nullable=False, index=True)
    event_type = Column(String(50), nullable=False)
    minute = Column(Integer)
    extra_minute = Column(Integer)
    team_id = Column(Integer, ForeignKey("teams.id"), index=True)
    player_id = Column(Integer, ForeignKey("players.id"), index=True)
    assist_player_id = Column(Integer, ForeignKey("players.id"))
    detail = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    fixture = relationship("Fixture", back_populates="events")

    __table_args__ = (
        Index("ix_event_fixture_type", "fixture_id", "event_type"),
    )


class PlayerAppearance(Base):
    __tablename__ = "player_appearances"

    id = Column(Integer, primary_key=True)
    fixture_id = Column(Integer, ForeignKey("fixtures.id"), nullable=False, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), index=True)
    position = Column(String(50))
    shirt_number = Column(Integer)
    minutes_played = Column(Integer)
    start_position = Column(Boolean, default=False)
    is_captain = Column(Boolean, default=False)
    goals = Column(Integer, default=0)
    assists = Column(Integer, default=0)
    yellow_cards = Column(Integer, default=0)
    red_cards = Column(Integer, default=0)
    shots_total = Column(Integer)
    shots_on_target = Column(Integer)
    passes_key = Column(Integer)
    passes_accuracy = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

    fixture = relationship("Fixture", back_populates="appearances")
    player = relationship("Player", back_populates="appearances")

    __table_args__ = (
        UniqueConstraint("fixture_id", "player_id", name="uq_fixture_player"),
    )


class TeamForm(Base):
    __tablename__ = "team_form"

    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False, index=True)
    competition_id = Column(Integer, ForeignKey("competitions.id"), index=True)
    fixture_id = Column(Integer, ForeignKey("fixtures.id"), index=True)
    form_type = Column(String(50), nullable=False)
    window_size = Column(Integer, nullable=False)
    wins = Column(Integer, default=0)
    draws = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    goals_for = Column(Integer, default=0)
    goals_against = Column(Integer, default=0)
    points = Column(Integer, default=0)
    calculated_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_team_form_lookup", "team_id", "competition_id", "form_type", "window_size"),
    )


class HeadToHead(Base):
    __tablename__ = "head_to_head"

    id = Column(Integer, primary_key=True)
    home_team_id = Column(Integer, ForeignKey("teams.id"), nullable=False, index=True)
    away_team_id = Column(Integer, ForeignKey("teams.id"), nullable=False, index=True)
    competition_id = Column(Integer, ForeignKey("competitions.id"), index=True)
    fixture_id = Column(Integer, ForeignKey("fixtures.id"), index=True)
    matches = Column(Integer, default=0)
    home_wins = Column(Integer, default=0)
    away_wins = Column(Integer, default=0)
    draws = Column(Integer, default=0)
    home_goals = Column(Integer, default=0)
    away_goals = Column(Integer, default=0)
    calculated_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_h2h_teams", "home_team_id", "away_team_id"),
    )


class VenueStats(Base):
    __tablename__ = "venue_stats"

    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False, index=True)
    venue = Column(String(255), nullable=False)
    competition_id = Column(Integer, ForeignKey("competitions.id"), index=True)
    matches = Column(Integer, default=0)
    wins = Column(Integer, default=0)
    draws = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    goals_for = Column(Integer, default=0)
    goals_against = Column(Integer, default=0)
    calculated_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_venue_lookup", "team_id", "venue"),
    )


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id = Column(Integer, primary_key=True)
    model_name = Column(String(100), nullable=False)
    version = Column(String(50), nullable=False)
    model_type = Column(String(50), nullable=False)
    metrics = Column(Text)
    feature_importance = Column(Text)
    trained_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=False)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True)
    fixture_id = Column(Integer, ForeignKey("fixtures.id"), nullable=False, index=True)
    model_version_id = Column(Integer, ForeignKey("model_versions.id"), index=True)
    prediction_type = Column(String(100), nullable=False)
    predicted_value = Column(Float, nullable=False)
    probability = Column(Float)
    confidence = Column(Float)
    is_accepted = Column(Boolean, default=False)
    actual_value = Column(Float)
    is_correct = Column(Boolean)
    predicted_at = Column(DateTime, default=datetime.utcnow)
    settled_at = Column(DateTime)

    __table_args__ = (
        Index("ix_prediction_lookup", "fixture_id", "prediction_type"),
    )


class DailyJob(Base):
    __tablename__ = "daily_jobs"

    id = Column(Integer, primary_key=True)
    job_type = Column(String(100), nullable=False)
    status = Column(String(50), nullable=False, default="PENDING")
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    records_processed = Column(Integer)
    errors = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class WeatherData(Base):
    __tablename__ = "weather_data"

    id = Column(Integer, primary_key=True)
    fixture_id = Column(Integer, ForeignKey("fixtures.id"), nullable=False, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    temperature_max = Column(Float)
    temperature_min = Column(Float)
    precipitation_prob = Column(Integer)
    weather_code = Column(Integer)
    wind_speed = Column(Float)
    fetched_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_weather_fixture", "fixture_id"),
    )


class OddsData(Base):
    __tablename__ = "odds_data"

    id = Column(Integer, primary_key=True)
    fixture_id = Column(Integer, ForeignKey("fixtures.id"), index=True)
    external_fixture_key = Column(String(100), index=True)
    sport = Column(String(100), nullable=False)
    bookmaker = Column(String(100), nullable=False)
    home_odds = Column(Float)
    draw_odds = Column(Float)
    away_odds = Column(Float)
    home_prob = Column(Float)
    draw_prob = Column(Float)
    away_prob = Column(Float)
    market_type = Column(String(50), default="h2h")
    fetched_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("odds_fixture_bookmaker", "fixture_id", "bookmaker"),
    )


class PredictionRecord(Base):
    """Extended prediction record with CLV tracking"""
    __tablename__ = "prediction_records"

    id = Column(Integer, primary_key=True)
    fixture_id = Column(Integer, ForeignKey("fixtures.id"), nullable=False, index=True)
    model_version_id = Column(Integer, ForeignKey("model_versions.id"), index=True)

    # Prediction details
    predicted_probability = Column(Float, nullable=False)
    predicted_odds = Column(Float, nullable=False)
    prediction_type = Column(String(50), default="home_win")

    # Market tracking at prediction time
    market_odds_at_prediction = Column(Float)
    market_bookmaker = Column(String(100))

    # Closing odds (fetched after match starts)
    closing_odds = Column(Float)
    closing_bookmaker = Column(String(100))
    closing_fetched_at = Column(DateTime)

    # CLV metrics
    implied_probability = Column(Float)  # from market odds
    closing_implied = Column(Float)  # from closing odds
    clv = Column(Float)  # Closing Line Value = prediction - closing_implied
    clv_percentage = Column(Float)  # CLV as percentage

    # Filtering metadata
    edge_score = Column(Float)
    agreement_score = Column(Float)
    variance_score = Column(Float)
    confidence_band = Column(String(20))

    # Decision
    is_accepted = Column(Boolean, default=False)
    stake_fraction = Column(Float)

    # Outcome
    actual_outcome = Column(String(20))
    is_correct = Column(Boolean)
    profit = Column(Float)
    settled_at = Column(DateTime)

    # Timestamps
    predicted_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_pred_record_fixture", "fixture_id", "prediction_type"),
        Index("ix_pred_record_clv", "clv"),
    )


class OddsHistory(Base):
    """Track odds movements over time"""
    __tablename__ = "odds_history"

    id = Column(Integer, primary_key=True)
    fixture_id = Column(Integer, ForeignKey("fixtures.id"), nullable=False, index=True)
    bookmaker = Column(String(100), nullable=False)
    home_odds = Column(Float)
    draw_odds = Column(Float)
    away_odds = Column(Float)
    market_type = Column(String(50), default="h2h")

    # Movement tracking
    movement_home = Column(Float)  # % change from first observed
    movement_away = Column(Float)
    hours_before_match = Column(Integer)  # hours until kickoff

    fetched_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_odds_history_fixture", "fixture_id", "bookmaker", "fetched_at"),
    )


class MarketSignal(Base):
    """Market efficiency and sharp money signals"""
    __tablename__ = "market_signals"

    id = Column(Integer, primary_key=True)
    fixture_id = Column(Integer, ForeignKey("fixtures.id"), nullable=False, index=True)

    # Sharp money indicators
    sharp_movement_pct = Column(Float)  # Late movement magnitude
    sharp_bookmaker = Column(String(100))
    soft_bookmaker = Column(String(100))
    sharp_soft_divergence = Column(Float)  # Difference between sharp/soft

    # Reverse line movement
    reverse_line_movement = Column(Boolean, default=False)

    # Efficiency metrics
    bookmaker_disagreement = Column(Float)  # Spread between bookmakers
    inefficiency_score = Column(Float)  # Model vs market divergence
    market_consensus_prob = Column(Float)  # Average implied probability

    # Pre-match context
    public_betting_pct = Column(Float)  # If available

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_market_signal_fixture", "fixture_id"),
    )


# MULTI-SPORT TABLES

class SportEvent(Base):
    """Universal sports event/fixture table"""
    __tablename__ = "sport_events"
    
    id = Column(Integer, primary_key=True)
    sport = Column(String(20), nullable=False, index=True)
    league = Column(String(20), nullable=False, index=True)
    external_event_id = Column(String(50), unique=True, nullable=False, index=True)
    
    home_team_id = Column(Integer, index=True)
    away_team_id = Column(Integer, index=True)
    home_team_name = Column(String(100))
    away_team_name = Column(String(100))
    
    competition_id = Column(Integer)
    season = Column(Integer)
    game_number = Column(Integer, default=1)
    
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime)
    
    status = Column(String(20), default="SCHEDULED", index=True)
    
    home_score = Column(Integer, default=0)
    away_score = Column(Integer, default=0)
    home_line_score = Column(String(50))
    away_line_score = Column(String(50))
    
    venue_name = Column(String(200))
    venue_location = Column(String(200))
    
    mlb_data = Column(JSON)
    nba_data = Column(JSON)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index("ix_sport_event_composite", "sport", "league", "start_time"),
    )


class SportTeam(Base):
    """Universal team table across sports"""
    __tablename__ = "sport_teams"
    
    id = Column(Integer, primary_key=True)
    sport = Column(String(20), nullable=False, index=True)
    external_team_id = Column(String(50), unique=True, nullable=False, index=True)
    
    name = Column(String(100), nullable=False)
    abbreviation = Column(String(10))
    city = Column(String(50))
    
    league_name = Column(String(20))
    division = Column(String(50))
    conference = Column(String(50))
    
    wins = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    draws = Column(Integer, default=0)
    games_played = Column(Integer, default=0)
    
    team_data = Column(JSON)
    
    created_at = Column(DateTime, default=datetime.utcnow)


class SportOdds(Base):
    """Universal odds table for all sports"""
    __tablename__ = "sport_odds"
    
    id = Column(Integer, primary_key=True)
    sport_event_id = Column(Integer, index=True)
    sport = Column(String(20), nullable=False, index=True)
    
    market = Column(String(30), nullable=False)
    bookmaker = Column(String(50))
    
    selection_name = Column(String(100))
    line = Column(Float)
    handicap = Column(Float)
    
    odds_decimal = Column(Float)
    odds_american = Column(Integer)
    odds_fractional = Column(String(10))
    
    implied_probability = Column(Float)
    
    fetched_at = Column(DateTime, default=datetime.utcnow)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index("ix_sport_odds_composite", "sport_event_id", "market"),
    )


class MLBPitcher(Base):
    """MLB-specific pitcher data"""
    __tablename__ = "mlb_pitchers"
    
    id = Column(Integer, primary_key=True)
    external_id = Column(Integer, unique=True, nullable=False, index=True)
    
    name = Column(String(100), nullable=False)
    team_id = Column(Integer, index=True)
    throws = Column(String(1))
    bats = Column(String(1))
    
    role = Column(String(20))
    
    era = Column(Float)
    whip = Column(Float)
    innings_pitched = Column(Float)
    strikeouts = Column(Integer)
    walks = Column(Integer)
    hits_allowed = Column(Integer)
    wins = Column(Integer)
    losses = Column(Integer)
    
    recent_era = Column(Float)
    vs_left_avg = Column(Float)
    vs_right_avg = Column(Float)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MLBBullpen(Base):
    """MLB bullpen status/fatigue tracking"""
    __tablename__ = "mlb_bullpens"
    
    id = Column(Integer, primary_key=True)
    game_id = Column(Integer, index=True)
    team_id = Column(Integer, index=True)
    
    pitch_count_today = Column(Integer, default=0)
    relief_pitchers_used = Column(Integer, default=0)
    
    high_leverage_pitches = Column(Integer, default=0)
    consecutive_days_pitched = Column(Integer, default=0)
    
    closer_available = Column(Boolean, default=True)
    setup_man_available = Column(Boolean, default=True)
    bullpen_exhausted = Column(Boolean, default=False)
    
    fetched_at = Column(DateTime, default=datetime.utcnow)


class Injury(Base):
    """Player injury tracking"""
    __tablename__ = "injuries"
    
    id = Column(Integer, primary_key=True)
    external_id = Column(String(50), unique=True, nullable=False, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), index=True)
    fixture_id = Column(Integer, ForeignKey("fixtures.id"), index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), index=True)
    
    type = Column(String(50), nullable=False)
    severity = Column(Float, nullable=False)
    status = Column(String(20), default="active")
    description = Column(Text)
    expected_return = Column(DateTime)
    actual_return = Column(DateTime)
    
    fetched_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index("ix_injuries_player_fixture", "player_id", "fixture_id"),
        Index("ix_injuries_team_match_date", "team_id", "fetched_at"),
    )


class Suspension(Base):
    """Player suspension tracking"""
    __tablename__ = "suspensions"
    
    id = Column(Integer, primary_key=True)
    external_id = Column(String(50), unique=True, nullable=False, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), index=True)
    fixture_id = Column(Integer, ForeignKey("fixtures.id"), index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), index=True)
    
    reason = Column(String(255))
    matches_remaining = Column(Integer, default=0)
    is_serving = Column(Boolean, default=True)
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    
    fetched_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index("ix_suspensions_player_fixture", "player_id", "fixture_id"),
    )


class Lineup(Base):
    """Confirmed team lineup"""
    __tablename__ = "lineups"
    
    id = Column(Integer, primary_key=True)
    fixture_id = Column(Integer, ForeignKey("fixtures.id"), nullable=False, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False, index=True)
    
    formation = Column(String(10))
    players_json = Column(Text)
    confirmed = Column(Boolean, default=False)
    
    fetched_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint("fixture_id", "team_id", name="uq_lineup_fixture_team"),
    )


class SettledPrediction(Base):
    """Enhanced settlement tracking with CLV and calibration"""
    __tablename__ = "settled_predictions"
    
    id = Column(Integer, primary_key=True)
    prediction_record_id = Column(Integer, ForeignKey("prediction_records.id"), nullable=False, index=True)
    fixture_id = Column(Integer, ForeignKey("fixtures.id"), nullable=False, index=True)
    
    actual_value = Column(Integer, nullable=False)
    actual_score = Column(String(20))
    
    closing_odds = Column(Float)
    closing_implied = Column(Float)
    clv = Column(Float)
    clv_percentage = Column(Float)
    
    calibration_drift = Column(Float)
    
    predicted_outcome = Column(String(10))
    actual_outcome = Column(String(10))
    is_correct = Column(Boolean)
    stake = Column(Float, nullable=False, default=0)
    odds = Column(Float, nullable=False)
    profit = Column(Float, default=0)
    
    settled_at = Column(DateTime, default=datetime.utcnow)
    source = Column(String(20), default="auto")
    notes = Column(Text)
    
    __table_args__ = (
        Index("ix_settled_fixture", "fixture_id"),
        Index("ix_settled_correct", "is_correct"),
        Index("ix_settled_clv", "clv"),
    )


class ModelHealthReport(Base):
    """Weekly model health report storage"""
    __tablename__ = "model_health_reports"
    
    id = Column(Integer, primary_key=True)
    report_date = Column(DateTime, nullable=False, index=True)
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    
    bl1_roi = Column(Float)
    bl1_bets = Column(Integer)
    bl1_win_rate = Column(Float)
    pl_roi = Column(Float)
    pl_bets = Column(Integer)
    pl_win_rate = Column(Float)
    other_roi = Column(Float)
    other_bets = Column(Integer)
    
    threshold_070_wins = Column(Integer)
    threshold_070_total = Column(Integer)
    threshold_055_wins = Column(Integer)
    threshold_055_total = Column(Integer)
    
    calibration_ece = Column(Float)
    calibration_mce = Column(Float)
    calibration_drift = Column(Float)
    
    peak_bankroll = Column(Float)
    current_bankroll = Column(Float)
    max_drawdown = Column(Float)
    max_drawdown_pct = Column(Float)
    
    recommendation = Column(String(50))
    recommendation_reason = Column(Text)
    parameters_changed = Column(Text)
    
    created_at = Column(DateTime, default=datetime.utcnow)


class DailyRun(Base):
    __tablename__ = "daily_runs"
    
    id = Column(Integer, primary_key=True)
    run_date = Column(Date, unique=True, index=True)
    status = Column(String(50), default="PENDING")
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    fixtures_fetched = Column(Integer, default=0)
    fixtures_processed = Column(Integer, default=0)
    predictions_generated = Column(Integer, default=0)
    predictions_quality_passed = Column(Integer, default=0)
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class DailySummary(Base):
    __tablename__ = "daily_summary"
    
    id = Column(Integer, primary_key=True)
    run_date = Column(Date, index=True)
    sport = Column(String(50))
    league = Column(String(50))
    total_fixtures = Column(Integer, default=0)
    open_predictions = Column(Integer, default=0)
    positive_ev_count = Column(Integer, default=0)
    high_confidence_count = Column(Integer, default=0)
    top_ev_opportunity = Column(Float, default=0.0)
    total_ev = Column(Float, default=0.0)
    last_pipeline_run = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
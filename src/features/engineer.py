"""Feature engineering module for PredUp"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

from sqlalchemy.orm import Session

from src.data.repositories import (
    FixtureRepository, TeamRepository, CompetitionRepository
)
from src.data.database import Fixture, Team, TeamForm, HeadToHead, VenueStats

logger = logging.getLogger(__name__)


class FeatureEngineer:
    def __init__(self, session: Session, config: Optional[Dict] = None):
        self.session = session
        self.config = config or {}
        self.fixture_repo = FixtureRepository(session)
        self.team_repo = TeamRepository(session)
        self.competition_repo = CompetitionRepository(session)

        self.lookback_forms = self.config.get("lookback_forms", [5, 10])
        self.lookback_h2h = self.config.get("lookback_h2h", 10)
        self.lookback_venue = self.config.get("lookback_venue", 20)

    def generate_features_for_fixture(
        self,
        fixture_id: int,
        include_targets: bool = True
    ) -> Dict[str, Any]:
        """Generate all features for a single fixture"""
        fixture = self.fixture_repo.get_by_id(fixture_id)
        if not fixture:
            raise ValueError(f"Fixture {fixture_id} not found")

        features = {}

        features.update(self._get_basic_info(fixture))
        features.update(self._get_form_features(fixture))
        features.update(self._get_h2h_features(fixture))
        features.update(self._get_venue_features(fixture))
        features.update(self._get_situational_features(fixture))
        
        # Phase 2: Advanced features (only for scheduled/pending fixtures)
        if fixture.status == "SCHEDULED":
            features.update(self._get_weather_features(fixture))
            features.update(self._get_odds_features(fixture))
            features.update(self._get_advanced_form_features(fixture))

        if include_targets:
            features.update(self._get_target_variables(fixture))

        return features

    def _get_basic_info(self, fixture: Fixture) -> Dict[str, Any]:
        """Basic fixture information"""
        return {
            "fixture_id": fixture.id,
            "external_id": fixture.external_id,
            "competition_id": fixture.competition_id,
            "season": fixture.season,
            "matchday": fixture.matchday,
            "utc_date": fixture.utc_date.isoformat() if fixture.utc_date else None,
            "home_team_id": fixture.home_team_id,
            "away_team_id": fixture.away_team_id,
            "is_home": 1,
        }

    def _get_form_features(self, fixture: Fixture) -> Dict[str, Any]:
        """Form-based features for both teams"""
        features = {}

        for team_id, team_type in [
            (fixture.home_team_id, "home"),
            (fixture.away_team_id, "away")
        ]:
            if not team_id:
                continue

            for window in self.lookback_forms:
                form_data = self._calculate_team_form(
                    team_id,
                    fixture.competition_id,
                    window,
                    fixture.utc_date
                )

                prefix = f"{team_type}_form_{window}"
                features[f"{prefix}_points"] = form_data.get("points", 0)
                features[f"{prefix}_wins"] = form_data.get("wins", 0)
                features[f"{prefix}_draws"] = form_data.get("draws", 0)
                features[f"{prefix}_losses"] = form_data.get("losses", 0)
                features[f"{prefix}_gf"] = form_data.get("goals_for", 0)
                features[f"{prefix}_ga"] = form_data.get("goals_against", 0)
                features[f"{prefix}_gd"] = form_data.get("goal_diff", 0)
                features[f"{prefix}_matches"] = form_data.get("matches", 0)

            form_diff = features.get("home_form_5_points", 0) - features.get("away_form_5_points", 0)
            features["form_diff_5"] = form_diff
            features["form_diff_10"] = (
                features.get("home_form_10_points", 0) - 
                features.get("away_form_10_points", 0)
            )

        return features

    def _calculate_team_form(
        self,
        team_id: int,
        competition_id: Optional[int],
        window: int,
        reference_date: Optional[datetime]
    ) -> Dict[str, int]:
        """Calculate team form over last N matches"""
        query = self.session.query(Fixture).filter(
            Fixture.id != None
        )

        if reference_date:
            query = query.filter(Fixture.utc_date < reference_date)

        query = query.filter(
            (Fixture.home_team_id == team_id) | (Fixture.away_team_id == team_id)
        )

        if competition_id:
            query = query.filter(Fixture.competition_id == competition_id)

        matches = query.order_by(Fixture.utc_date.desc()).limit(window).all()

        wins = draws = losses = goals_for = goals_against = 0

        for match in matches:
            if match.status != "FINISHED":
                continue

            is_home = match.home_team_id == team_id
            team_score = match.home_score if is_home else match.away_score
            opp_score = match.away_score if is_home else match.home_score

            if team_score is None or opp_score is None:
                continue

            goals_for += team_score
            goals_against += opp_score

            if team_score > opp_score:
                wins += 1
            elif team_score == opp_score:
                draws += 1
            else:
                losses += 1

        points = wins * 3 + draws
        matches_played = wins + draws + losses

        return {
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "goals_for": goals_for,
            "goals_against": goals_against,
            "goal_diff": goals_for - goals_against,
            "points": points,
            "matches": matches_played,
        }

    def _get_h2h_features(self, fixture: Fixture) -> Dict[str, Any]:
        """Head-to-head features"""
        if not fixture.home_team_id or not fixture.away_team_id:
            return {}

        h2h = self.session.query(HeadToHead).filter(
            HeadToHead.home_team_id == fixture.home_team_id,
            HeadToHead.away_team_id == fixture.away_team_id,
        ).first()

        if not h2h:
            return {
                "h2h_matches": 0,
                "h2h_home_wins": 0,
                "h2h_away_wins": 0,
                "h2h_draws": 0,
                "h2h_home_goals": 0,
                "h2h_away_goals": 0,
            }

        return {
            "h2h_matches": h2h.matches or 0,
            "h2h_home_wins": h2h.home_wins or 0,
            "h2h_away_wins": h2h.away_wins or 0,
            "h2h_draws": h2h.draws or 0,
            "h2h_home_goals": h2h.home_goals or 0,
            "h2h_away_goals": h2h.away_goals or 0,
        }

    def _get_venue_features(self, fixture: Fixture) -> Dict[str, Any]:
        """Venue-specific features"""
        features = {}

        if fixture.home_team_id and fixture.venue:
            venue_stats = self.session.query(VenueStats).filter(
                VenueStats.team_id == fixture.home_team_id,
                VenueStats.venue == fixture.venue,
            ).first()

            if venue_stats:
                features["home_venue_matches"] = venue_stats.matches or 0
                features["home_venue_wins"] = venue_stats.wins or 0
                features["home_venue_draws"] = venue_stats.draws or 0
                features["home_venue_losses"] = venue_stats.losses or 0
                features["home_venue_gf"] = venue_stats.goals_for or 0
                features["home_venue_ga"] = venue_stats.goals_against or 0

        return features

    def _get_situational_features(self, fixture: Fixture) -> Dict[str, Any]:
        """Situational features (day rest, competition, etc.)"""
        features = {}

        if fixture.utc_date:
            features["day_of_week"] = fixture.utc_date.weekday()
            features["hour"] = fixture.utc_date.hour
            features["is_weekend"] = 1 if fixture.utc_date.weekday() >= 5 else 0

        features["matchday"] = fixture.matchday or 0
        features["season"] = fixture.season or 0
        
        # Rest days (days since last match for each team)
        rest_features = self._calculate_rest_days(fixture)
        features.update(rest_features)

        return features
    
    def _calculate_rest_days(self, fixture: Fixture) -> Dict[str, int]:
        """Calculate days since each team's last match"""
        features = {}
        
        for team_id, prefix in [
            (fixture.home_team_id, "home"),
            (fixture.away_team_id, "away")
        ]:
            if not team_id or not fixture.utc_date:
                features[f"{prefix}_rest_days"] = 7
                continue
            
            last_match = self.session.query(Fixture).filter(
                Fixture.home_team_id == team_id,
                Fixture.away_team_id == team_id,
                Fixture.utc_date < fixture.utc_date,
                Fixture.status == "FINISHED"
            ).order_by(Fixture.utc_date.desc()).first()
            
            if not last_match:
                # Also check away team
                last_match = self.session.query(Fixture).filter(
                    Fixture.away_team_id == team_id,
                    Fixture.utc_date < fixture.utc_date,
                    Fixture.status == "FINISHED"
                ).order_by(Fixture.utc_date.desc()).first()
            
            if last_match and last_match.utc_date:
                days = (fixture.utc_date - last_match.utc_date).days
                features[f"{prefix}_rest_days"] = min(days, 21)  # Cap at 3 weeks
            else:
                features[f"{prefix}_rest_days"] = 14  # Default to 2 weeks if no history
        
        # Rest differential
        home_rest = features.get("home_rest_days", 14)
        away_rest = features.get("away_rest_days", 14)
        features["rest_diff"] = home_rest - away_rest
        
        return features

    def _get_weather_features(self, fixture: Fixture) -> Dict[str, Any]:
        """Weather features for the fixture (forward-only)"""
        from src.data.database import WeatherData
        
        features = {}
        
        if fixture.status != "SCHEDULED":
            return features
        
        weather = self.session.query(WeatherData).filter(
            WeatherData.fixture_id == fixture.id
        ).first()
        
        if weather:
            features["weather_temp_max"] = weather.temperature_max or 15.0
            features["weather_temp_min"] = weather.temperature_min or 10.0
            features["weather_precip_prob"] = weather.precipitation_prob or 0
            features["weather_wind_speed"] = weather.wind_speed or 0.0
            
            # Weather impact modifier
            # Rain/snow reduces scoring; clear skies increase
            code = weather.weather_code or 0
            if code <= 1:  # Clear
                features["weather_impact"] = 1.0
            elif code <= 3:  # Cloudy
                features["weather_impact"] = 0.95
            elif code <= 50:  # Rain
                features["weather_impact"] = 0.85
            else:  # Snow/heavy rain
                features["weather_impact"] = 0.75
        else:
            # Default values if no weather data
            features["weather_temp_max"] = 15.0
            features["weather_temp_min"] = 10.0
            features["weather_precip_prob"] = 30
            features["weather_wind_speed"] = 10.0
            features["weather_impact"] = 1.0
        
        return features

    def _get_odds_features(self, fixture: Fixture) -> Dict[str, Any]:
        """Odds-derived features (implied probabilities, EV)"""
        from src.data.database import OddsData
        
        features = {}
        
        if fixture.status != "SCHEDULED":
            return features
        
        # Get latest odds for this fixture
        odds_records = self.session.query(OddsData).filter(
            OddsData.fixture_id == fixture.id
        ).order_by(OddsData.fetched_at.desc()).limit(5).all()
        
        if not odds_records:
            return features
        
        # Average odds across bookmakers
        home_odds = [o.home_odds for o in odds_records if o.home_odds]
        draw_odds = [o.draw_odds for o in odds_records if o.draw_odds]
        away_odds = [o.away_odds for o in odds_records if o.away_odds]
        
        if home_odds:
            avg_home = sum(home_odds) / len(home_odds)
            features["odds_home_implied"] = 1.0 / avg_home if avg_home > 0 else 0.5
        else:
            features["odds_home_implied"] = 0.5
            
        if away_odds:
            avg_away = sum(away_odds) / len(away_odds)
            features["odds_away_implied"] = 1.0 / avg_away if avg_away > 0 else 0.5
        else:
            features["odds_away_implied"] = 0.5
            
        if draw_odds:
            avg_draw = sum(draw_odds) / len(draw_odds)
            features["odds_draw_implied"] = 1.0 / avg_draw if avg_draw > 0 else 0.25
        else:
            features["odds_draw_implied"] = 0.25
        
        # Market overround (vig) - higher = more bookmaker margin
        total_implied = (
            features.get("odds_home_implied", 0) + 
            features.get("odds_draw_implied", 0) + 
            features.get("odds_away_implied", 0)
        )
        features["market_overround"] = total_implied if total_implied > 0 else 1.0
        
        # Fair odds (normalized without overround)
        if total_implied > 1.0:
            features["fair_home_prob"] = features.get("odds_home_implied", 0) / total_implied
            features["fair_away_prob"] = features.get("odds_away_implied", 0) / total_implied
        else:
            features["fair_home_prob"] = features.get("odds_home_implied", 0.33)
            features["fair_away_prob"] = features.get("odds_away_implied", 0.33)
        
        return features

    def _get_advanced_form_features(self, fixture: Fixture) -> Dict[str, Any]:
        """Advanced form features: streaks, clean sheets, scoring rates"""
        features = {}
        
        for team_id, prefix in [
            (fixture.home_team_id, "home"),
            (fixture.away_team_id, "away")
        ]:
            if not team_id:
                continue
            
            # Get last N matches
            matches = self.session.query(Fixture).filter(
                (Fixture.home_team_id == team_id) | (Fixture.away_team_id == team_id),
                Fixture.id != fixture.id,
                Fixture.utc_date < fixture.utc_date if fixture.utc_date else True,
                Fixture.status == "FINISHED"
            ).order_by(Fixture.utc_date.desc()).limit(15).all()
            
            if not matches:
                # Defaults
                features[f"{prefix}_win_streak"] = 0
                features[f"{prefix}_clean_sheet_pct"] = 0.5
                features[f"{prefix}_goals_per_game"] = 1.5
                features[f"{prefix}_btts_frequency"] = 0.5
                features[f"{prefix}_overs_frequency"] = 0.5
                continue
            
            wins = 0
            losses = 0
            clean_sheets = 0
            btts = 0
            overs = 0
            goals_for = 0
            goals_against = 0
            total = len(matches)
            
            for m in matches:
                is_home = m.home_team_id == team_id
                gf = m.home_score if is_home else m.away_score
                ga = m.away_score if is_home else m.home_score
                
                if gf is None or ga is None:
                    continue
                    
                goals_for += gf
                goals_against += ga
                
                if gf > 0 and ga > 0:
                    btts += 1
                if gf + ga > 2.5:
                    overs += 1
                if ga == 0:
                    clean_sheets += 1
                if gf > ga:
                    wins += 1
                elif gf < ga:
                    losses += 1
            
            # Calculate streaks
            win_streak = 0
            for m in matches:
                is_home = m.home_team_id == team_id
                gf = m.home_score if is_home else m.away_score
                ga = m.away_score if is_home else m.home_score
                if gf is None or ga is None:
                    break
                if gf > ga:
                    win_streak += 1
                else:
                    break
            
            played = wins + losses
            if played > 0:
                features[f"{prefix}_win_streak"] = win_streak
                features[f"{prefix}_clean_sheet_pct"] = clean_sheets / min(played, 10)
                features[f"{prefix}_goals_per_game"] = goals_for / min(played, 10)
                features[f"{prefix}_btts_frequency"] = btts / min(played, 10)
                features[f"{prefix}_overs_frequency"] = overs / min(played, 10)
            else:
                features[f"{prefix}_win_streak"] = 0
                features[f"{prefix}_clean_sheet_pct"] = 0.5
                features[f"{prefix}_goals_per_game"] = 1.5
                features[f"{prefix}_btts_frequency"] = 0.5
                features[f"{prefix}_overs_frequency"] = 0.5
        
        # Form differential features
        home_gpg = features.get("home_goals_per_game", 1.5)
        away_gpg = features.get("away_goals_per_game", 1.5)
        features["goals_per_game_diff"] = home_gpg - away_gpg
        
        home_cs = features.get("home_clean_sheet_pct", 0.5)
        away_cs = features.get("away_clean_sheet_pct", 0.5)
        features["clean_sheet_diff"] = home_cs - away_cs
        
        return features

    def _get_target_variables(self, fixture: Fixture) -> Dict[str, Any]:
        """Generate target variables for finished matches"""
        if fixture.status != "FINISHED":
            return {
                "target_over_25": None,
                "target_under_25": None,
                "target_btts": None,
                "total_goals": None,
            }

        total_goals = (fixture.home_score or 0) + (fixture.away_score or 0)

        return {
            "target_over_25": 1 if total_goals > 2 else 0,
            "target_under_25": 1 if total_goals <= 2 else 0,
            "target_btts": 1 if (fixture.home_score and fixture.away_score) else 0,
            "total_goals": total_goals,
        }

    def generate_dataset(
        self,
        competition_id: Optional[int] = None,
        min_date: Optional[datetime] = None,
        max_date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """Generate full dataset for model training"""
        logger.info("Generating feature dataset...")

        query = self.session.query(Fixture).filter(
            Fixture.status == "FINISHED"
        )

        if competition_id:
            query = query.filter(Fixture.competition_id == competition_id)

        if min_date:
            query = query.filter(Fixture.utc_date >= min_date)

        if max_date:
            query = query.filter(Fixture.utc_date <= max_date)

        fixtures = query.order_by(Fixture.utc_date).all()
        logger.info(f"Found {len(fixtures)} completed fixtures")

        records = []
        for fixture in fixtures:
            try:
                features = self.generate_features_for_fixture(
                    fixture.id,
                    include_targets=True
                )
                records.append(features)
            except Exception as e:
                logger.warning(f"Error generating features for fixture {fixture.id}: {e}")

        df = pd.DataFrame(records)
        logger.info(f"Generated dataset with {len(df)} rows and {len(df.columns)} columns")

        return df

    def update_h2h_features(self, fixture_id: int) -> None:
        """Update head-to-head after match completion"""
        fixture = self.fixture_repo.get_by_id(fixture_id)
        if not fixture or fixture.status != "FINISHED":
            return

        if not fixture.home_team_id or not fixture.away_team_id:
            return

        existing = self.session.query(HeadToHead).filter(
            HeadToHead.home_team_id == fixture.home_team_id,
            HeadToHead.away_team_id == fixture.away_team_id,
        ).first()

        if existing:
            existing.matches = (existing.matches or 0) + 1
            if fixture.home_score and fixture.away_score:
                if fixture.home_score > fixture.away_score:
                    existing.home_wins = (existing.home_wins or 0) + 1
                elif fixture.home_score < fixture.away_score:
                    existing.away_wins = (existing.away_wins or 0) + 1
                else:
                    existing.draws = (existing.draws or 0) + 1
                existing.home_goals = (existing.home_goals or 0) + fixture.home_score
                existing.away_goals = (existing.away_goals or 0) + fixture.away_score
            existing.calculated_at = datetime.utcnow()
        else:
            h2h = HeadToHead(
                home_team_id=fixture.home_team_id,
                away_team_id=fixture.away_team_id,
                competition_id=fixture.competition_id,
                fixture_id=fixture.id,
                matches=1,
                home_wins=1 if fixture.home_score and fixture.home_score > fixture.away_score else 0,
                away_wins=1 if fixture.home_score and fixture.home_score < fixture.away_score else 0,
                draws=1 if fixture.home_score == fixture.away_score else 0,
                home_goals=fixture.home_score or 0,
                away_goals=fixture.away_score or 0,
            )
            self.session.add(h2h)

        self.session.commit()
        logger.info(f"Updated H2H for fixture {fixture_id}")
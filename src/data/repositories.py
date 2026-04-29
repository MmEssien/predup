"""Repository pattern for database access"""

from typing import List, Optional, Any
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, asc

from src.data.database import (
    Team, Player, Competition, Fixture, FixtureEvent,
    PlayerAppearance, TeamForm, HeadToHead, VenueStats,
    ModelVersion, Prediction, DailyJob, WeatherData, OddsData
)


class BaseRepository:
    def __init__(self, session: Session):
        self.session = session

    def commit(self):
        self.session.commit()

    def rollback(self):
        self.session.rollback()


class TeamRepository(BaseRepository):
    def get_by_external_id(self, external_id: int) -> Optional[Team]:
        return self.session.query(Team).filter(Team.external_id == external_id).first()

    def get_by_id(self, team_id: int) -> Optional[Team]:
        return self.session.query(Team).filter(Team.id == team_id).first()

    def get_all(self, limit: int = 100) -> List[Team]:
        return self.session.query(Team).limit(limit).all()

    def create(self, data: dict) -> Team:
        team = Team(**data)
        self.session.add(team)
        self.commit()
        return team

    def upsert(self, external_id: int, data: dict) -> Team:
        team = self.get_by_external_id(external_id)
        if team:
            for key, value in data.items():
                setattr(team, key, value)
        else:
            team = self.create(data)
        self.commit()
        return team


class CompetitionRepository(BaseRepository):
    def get_by_external_id(self, external_id: int) -> Optional[Competition]:
        return self.session.query(Competition).filter(
            Competition.external_id == external_id
        ).first()

    def get_by_code(self, code: str) -> Optional[Competition]:
        return self.session.query(Competition).filter(
            Competition.code == code
        ).first()

    def get_all(self) -> List[Competition]:
        return self.session.query(Competition).all()

    def create(self, data: dict) -> Competition:
        comp = Competition(**data)
        self.session.add(comp)
        self.commit()
        return comp

    def upsert(self, external_id: int, data: dict) -> Competition:
        comp = self.get_by_external_id(external_id)
        if comp:
            for key, value in data.items():
                setattr(comp, key, value)
        else:
            comp = self.create(data)
        self.commit()
        return comp


class FixtureRepository(BaseRepository):
    def get_by_external_id(self, external_id: int) -> Optional[Fixture]:
        return self.session.query(Fixture).filter(
            Fixture.external_id == external_id
        ).first()

    def get_by_id(self, fixture_id: int) -> Optional[Fixture]:
        return self.session.query(Fixture).filter(Fixture.id == fixture_id).first()

    def get_upcoming(self, limit: int = 50) -> List[Fixture]:
        return self.session.query(Fixture).filter(
            Fixture.status == "SCHEDULED"
        ).order_by(Fixture.utc_date).limit(limit).all()

    def get_completed(self, competition_id: Optional[int] = None, limit: int = 100) -> List[Fixture]:
        query = self.session.query(Fixture).filter(
            Fixture.status == "FINISHED"
        )
        if competition_id:
            query = query.filter(Fixture.competition_id == competition_id)
        return query.order_by(desc(Fixture.utc_date)).limit(limit).all()

    def get_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        competition_id: Optional[int] = None
    ) -> List[Fixture]:
        query = self.session.query(Fixture).filter(
            and_(
                Fixture.utc_date >= start_date,
                Fixture.utc_date <= end_date
            )
        )
        if competition_id:
            query = query.filter(Fixture.competition_id == competition_id)
        return query.order_by(Fixture.utc_date).all()

    def create(self, data: dict) -> Fixture:
        fixture = Fixture(**data)
        self.session.add(fixture)
        self.commit()
        return fixture

    def upsert(self, external_id: int, data: dict) -> Fixture:
        fixture = self.get_by_external_id(external_id)
        if fixture:
            for key, value in data.items():
                setattr(fixture, key, value)
        else:
            fixture = self.create(data)
        self.commit()
        return fixture


class PredictionRepository(BaseRepository):
    def get_by_fixture(self, fixture_id: int, prediction_type: str) -> Optional[Prediction]:
        return self.session.query(Prediction).filter(
            and_(
                Prediction.fixture_id == fixture_id,
                Prediction.prediction_type == prediction_type
            )
        ).first()

    def get_pending_settlement(self, limit: int = 100) -> List[Prediction]:
        return self.session.query(Prediction).filter(
            Prediction.settled_at.is_(None)
        ).order_by(desc(Prediction.predicted_at)).limit(limit).all()

    def get_accepted(self, limit: int = 100) -> List[Prediction]:
        return self.session.query(Prediction).filter(
            Prediction.is_accepted == True
        ).order_by(desc(Prediction.predicted_at)).limit(limit).all()

    def create(self, data: dict) -> Prediction:
        prediction = Prediction(**data)
        self.session.add(prediction)
        self.commit()
        return prediction

    def settle(
        self,
        prediction_id: int,
        actual_value: float,
        is_correct: bool
    ) -> Prediction:
        prediction = self.session.query(Prediction).filter(
            Prediction.id == prediction_id
        ).first()
        if prediction:
            prediction.actual_value = actual_value
            prediction.is_correct = is_correct
            prediction.settled_at = datetime.utcnow()
            self.commit()
        return prediction


class ModelVersionRepository(BaseRepository):
    def get_active(self) -> Optional[ModelVersion]:
        return self.session.query(ModelVersion).filter(
            ModelVersion.is_active == True
        ).first()

    def get_by_name(self, model_name: str) -> List[ModelVersion]:
        return self.session.query(ModelVersion).filter(
            ModelVersion.model_name == model_name
        ).order_by(desc(ModelVersion.trained_at)).all()

    def create(self, data: dict) -> ModelVersion:
        version = ModelVersion(**data)
        self.session.add(version)
        self.commit()
        return version

    def deactivate_all(self, model_name: str) -> None:
        self.session.query(ModelVersion).filter(
            ModelVersion.model_name == model_name
        ).update({"is_active": False})
        self.commit()

    def set_active(self, version_id: int, model_name: str) -> ModelVersion:
        self.deactivate_all(model_name)
        version = self.session.query(ModelVersion).filter(
            ModelVersion.id == version_id
        ).first()
        if version:
            version.is_active = True
            self.commit()
        return version


class WeatherRepository(BaseRepository):
    def get_by_fixture(self, fixture_id: int) -> Optional[WeatherData]:
        return self.session.query(WeatherData).filter(
            WeatherData.fixture_id == fixture_id
        ).first()

    def create(self, data: dict) -> WeatherData:
        weather = WeatherData(**data)
        self.session.add(weather)
        self.commit()
        return weather

    def upsert(self, fixture_id: int, data: dict) -> WeatherData:
        existing = self.get_by_fixture(fixture_id)
        if existing:
            for key, value in data.items():
                setattr(existing, key, value)
        else:
            existing = self.create({**data, "fixture_id": fixture_id})
        self.commit()
        return existing


class OddsRepository(BaseRepository):
    def get_by_fixture(self, fixture_id: int) -> List[OddsData]:
        return self.session.query(OddsData).filter(
            OddsData.fixture_id == fixture_id
        ).all()

    def get_by_bookmaker(self, fixture_id: int, bookmaker: str) -> Optional[OddsData]:
        return self.session.query(OddsData).filter(
            and_(
                OddsData.fixture_id == fixture_id,
                OddsData.bookmaker == bookmaker
            )
        ).first()

    def create(self, data: dict) -> OddsData:
        odds = OddsData(**data)
        self.session.add(odds)
        self.commit()
        return odds

    def upsert(self, fixture_id: int, bookmaker: str, data: dict) -> OddsData:
        existing = self.get_by_bookmaker(fixture_id, bookmaker)
        if existing:
            for key, value in data.items():
                setattr(existing, key, value)
        else:
            existing = self.create({**data, "fixture_id": fixture_id, "bookmaker": bookmaker})
        self.commit()
        return existing

    def delete_old_for_fixture(self, fixture_id: int) -> None:
        self.session.query(OddsData).filter(
            OddsData.fixture_id == fixture_id
        ).delete()
        self.commit()
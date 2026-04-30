"""Database connection and session management"""

import os
import logging
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool

from src.data.database import Base
from src.utils.helpers import load_config

logger = logging.getLogger(__name__)


class DatabaseConfig:
    def __init__(self):
        config = load_config()
        db_config = config.get("database", {})

        self.url = os.getenv("DATABASE_URL")
        
        if not self.url:
            raise Exception("DATABASE_URL is not set in environment variables. Railway deployment requires DATABASE_URL.")

        self.pool_size = db_config.get("pool_size", 5)
        self.max_overflow = db_config.get("max_overflow", 10)


class DatabaseManager:
    _instance: Optional["DatabaseManager"] = None

    def __init__(self):
        self.config = DatabaseConfig()
        self.engine = None
        self.session_factory = None

    @classmethod
    def get_instance(cls) -> "DatabaseManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def initialize(self) -> None:
        if self.engine is not None:
            return

        logger.info(f"Initializing database: {self.config.host}:{self.config.port}")

        self.engine = create_engine(
            self.config.url,
            poolclass=QueuePool,
            pool_size=self.config.pool_size,
            max_overflow=self.config.max_overflow,
            pool_pre_ping=True,
            echo=os.getenv("SQL_ECHO", "false").lower() == "true",
        )

        self.session_factory = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
            autocommit=False,
        )

        event.listen(
            self.engine,
            "connect",
            self._set_search_path
        )

    @staticmethod
    def _set_search_path(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("SET search_path TO public")
        cursor.close()

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        if self.session_factory is None:
            self.initialize()

        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def create_all(self) -> None:
        self.initialize()
        Base.metadata.create_all(self.engine)
        logger.info("Database tables created")

    def drop_all(self) -> None:
        self.initialize()
        Base.metadata.drop_all(self.engine)
        logger.info("Database tables dropped")

    def get_session(self) -> Session:
        if self.session_factory is None:
            self.initialize()
        return self.session_factory()

    def close(self) -> None:
        if self.engine:
            self.engine.dispose()
            self.engine = None
            self.session_factory = None
            logger.info("Database connection closed")


db_manager = DatabaseManager.get_instance()


def get_db_session() -> Session:
    return db_manager.get_session()


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    with db_manager.session() as session:
        yield session
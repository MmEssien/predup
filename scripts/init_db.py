"""Database initialization script"""

import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.connection import DatabaseManager, db_manager
from src.data.database import Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_database(create_tables: bool = True, drop_existing: bool = False):
    """Initialize database schema"""
    try:
        logger.info("Initializing database...")
        db_manager.initialize()

        if drop_existing:
            logger.warning("Dropping existing tables...")
            db_manager.drop_all()

        if create_tables:
            logger.info("Creating tables...")
            db_manager.create_all()

        logger.info("Database initialization complete")
        return True

    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        return False


def reset_database():
    """Reset database - drop and recreate all tables"""
    return init_database(create_tables=True, drop_existing=True)


def check_connection() -> bool:
    """Check database connection"""
    try:
        db_manager.initialize()
        with db_manager.session() as session:
            result = session.execute("SELECT 1").fetchone()
        logger.info("Database connection OK")
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Database management script")
    parser.add_argument("--reset", action="store_true", help="Reset database (drop all tables)")
    parser.add_argument("--check", action="store_true", help="Check database connection")
    args = parser.parse_args()

    if args.reset:
        reset_database()
    elif args.check:
        check_connection()
    else:
        init_database()


if __name__ == "__main__":
    main()
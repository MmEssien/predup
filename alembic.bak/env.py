"""Alembic env configuration"""

from logging.config import fileConfig
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parents[2]))

load_dotenv(Path(__file__).parents[2] / ".env")

from alembic import context
from sqlalchemy import engine_from_config, pool

from src.data.database import Base
from src.utils.helpers import load_config
import src.data.database

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url():
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    
    config_obj = load_config()
    db_config = config_obj.get("database", {})

    host = os.getenv("DATABASE_HOST", db_config.get("host", "localhost"))
    port = os.getenv("DATABASE_PORT", db_config.get("port", 5432))
    name = os.getenv("DATABASE_NAME", db_config.get("name", "predup"))
    user = os.getenv("DATABASE_USER", "postgres")
    password = os.getenv("DATABASE_PASSWORD", "postgres")

    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
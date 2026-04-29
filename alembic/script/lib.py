from alembic import context
from sqlalchemy import meta

from lib import lib_299_1  # noqa: F401

config = context.config

if meta.metadata is not None:
    target_metadata = meta.metadata
else:
    target_metadata = None


def get_metadata():
    return target_metadata
"""Initial migration

Revision ID: 001_initial
Revises:
Create Date: 2024-01-01

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'teams',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('external_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('short_name', sa.String(length=50), nullable=True),
        sa.Column('tla', sa.String(length=10), nullable=True),
        sa.Column('crest_url', sa.String(length=500), nullable=True),
        sa.Column('venue', sa.String(length=255), nullable=True),
        sa.Column('league', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    # Create index if not exists (idempotent for PostgreSQL)
    conn = op.get_bind()
    result = conn.execute(sa.text("SELECT 1 FROM pg_indexes WHERE indexname = 'ix_teams_external_id'")).fetchone()
    if not result:
        op.create_index(op.f('ix_teams_external_id'), 'teams', ['external_id'], unique=True)

    op.create_table(
        'competitions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('external_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('code', sa.String(length=20), nullable=False),
        sa.Column('area_name', sa.String(length=100), nullable=True),
        sa.Column('emblem_url', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_competitions_code'), 'competitions', ['code'], unique=False)
    op.create_index(op.f('ix_competitions_external_id'), 'competitions', ['external_id'], unique=True)


def downgrade() -> None:
    op.drop_table('teams')
    op.drop_table('competitions')
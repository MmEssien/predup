"""Multi-sport tables migration

Revision ID: 002_multi_sport
Revises: 001_initial
Create Date: 2026-04-27

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '002_multi_sport'
down_revision: Union[str, None] = '001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Sport Events table
    op.create_table(
        'sport_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sport', sa.String(length=20), nullable=False),
        sa.Column('league', sa.String(length=20), nullable=False),
        sa.Column('external_event_id', sa.String(length=50), nullable=False),
        sa.Column('home_team_id', sa.Integer(), nullable=True),
        sa.Column('away_team_id', sa.Integer(), nullable=True),
        sa.Column('home_team_name', sa.String(length=100), nullable=True),
        sa.Column('away_team_name', sa.String(length=100), nullable=True),
        sa.Column('competition_id', sa.Integer(), nullable=True),
        sa.Column('season', sa.Integer(), nullable=True),
        sa.Column('game_number', sa.Integer(), nullable=True, default=1),
        sa.Column('start_time', sa.DateTime(), nullable=False),
        sa.Column('end_time', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True, default='SCHEDULED'),
        sa.Column('home_score', sa.Integer(), nullable=True, default=0),
        sa.Column('away_score', sa.Integer(), nullable=True, default=0),
        sa.Column('home_line_score', sa.String(length=50), nullable=True),
        sa.Column('away_line_score', sa.String(length=50), nullable=True),
        sa.Column('venue_name', sa.String(length=200), nullable=True),
        sa.Column('venue_location', sa.String(length=200), nullable=True),
        sa.Column('mlb_data', sa.JSON(), nullable=True),
        sa.Column('nba_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_sport_events_sport', 'sport_events', ['sport'])
    op.create_index('ix_sport_events_league', 'sport_events', ['league'])
    op.create_index('ix_sport_events_start_time', 'sport_events', ['start_time'])
    op.create_index('ix_sport_events_status', 'sport_events', ['status'])
    op.create_index('ix_sport_event_external_id', 'sport_events', ['external_event_id'], unique=True)
    op.create_index('ix_sport_event_composite', 'sport_events', ['sport', 'league', 'start_time'])

    # Sport Teams table
    op.create_table(
        'sport_teams',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sport', sa.String(length=20), nullable=False),
        sa.Column('external_team_id', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('abbreviation', sa.String(length=10), nullable=True),
        sa.Column('city', sa.String(length=50), nullable=True),
        sa.Column('league_name', sa.String(length=20), nullable=True),
        sa.Column('division', sa.String(length=50), nullable=True),
        sa.Column('conference', sa.String(length=50), nullable=True),
        sa.Column('wins', sa.Integer(), nullable=True, default=0),
        sa.Column('losses', sa.Integer(), nullable=True, default=0),
        sa.Column('draws', sa.Integer(), nullable=True, default=0),
        sa.Column('games_played', sa.Integer(), nullable=True, default=0),
        sa.Column('team_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_sport_teams_sport', 'sport_teams', ['sport'])
    op.create_index('ix_sport_teams_external_id', 'sport_teams', ['external_team_id'], unique=True)

    # Sport Odds table
    op.create_table(
        'sport_odds',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sport_event_id', sa.Integer(), nullable=True),
        sa.Column('sport', sa.String(length=20), nullable=False),
        sa.Column('market', sa.String(length=30), nullable=False),
        sa.Column('bookmaker', sa.String(length=50), nullable=True),
        sa.Column('selection_name', sa.String(length=100), nullable=True),
        sa.Column('line', sa.Float(), nullable=True),
        sa.Column('handicap', sa.Float(), nullable=True),
        sa.Column('odds_decimal', sa.Float(), nullable=True),
        sa.Column('odds_american', sa.Integer(), nullable=True),
        sa.Column('odds_fractional', sa.String(length=10), nullable=True),
        sa.Column('implied_probability', sa.Float(), nullable=True),
        sa.Column('fetched_at', sa.DateTime(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_sport_odds_sport', 'sport_odds', ['sport'])
    op.create_index('ix_sport_odds_event_id', 'sport_odds', ['sport_event_id'])
    op.create_index('ix_sport_odds_composite', 'sport_odds', ['sport_event_id', 'market'])

    # MLB Pitcher table
    op.create_table(
        'mlb_pitchers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('external_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('team_id', sa.Integer(), nullable=True),
        sa.Column('throws', sa.String(length=1), nullable=True),
        sa.Column('bats', sa.String(length=1), nullable=True),
        sa.Column('role', sa.String(length=20), nullable=True),
        sa.Column('era', sa.Float(), nullable=True),
        sa.Column('whip', sa.Float(), nullable=True),
        sa.Column('innings_pitched', sa.Float(), nullable=True),
        sa.Column('strikeouts', sa.Integer(), nullable=True),
        sa.Column('walks', sa.Integer(), nullable=True),
        sa.Column('hits_allowed', sa.Integer(), nullable=True),
        sa.Column('wins', sa.Integer(), nullable=True),
        sa.Column('losses', sa.Integer(), nullable=True),
        sa.Column('recent_era', sa.Float(), nullable=True),
        sa.Column('vs_left_avg', sa.Float(), nullable=True),
        sa.Column('vs_right_avg', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_mlb_pitchers_external_id', 'mlb_pitchers', ['external_id'], unique=True)
    op.create_index('ix_mlb_pitchers_team_id', 'mlb_pitchers', ['team_id'])

    # MLB Bullpen table
    op.create_table(
        'mlb_bullpens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('game_id', sa.Integer(), nullable=True),
        sa.Column('team_id', sa.Integer(), nullable=True),
        sa.Column('pitch_count_today', sa.Integer(), nullable=True, default=0),
        sa.Column('relief_pitchers_used', sa.Integer(), nullable=True, default=0),
        sa.Column('high_leverage_pitches', sa.Integer(), nullable=True, default=0),
        sa.Column('consecutive_days_pitched', sa.Integer(), nullable=True, default=0),
        sa.Column('closer_available', sa.Boolean(), nullable=True, default=True),
        sa.Column('setup_man_available', sa.Boolean(), nullable=True, default=True),
        sa.Column('bullpen_exhausted', sa.Boolean(), nullable=True, default=False),
        sa.Column('fetched_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_mlb_bullpens_game_id', 'mlb_bullpens', ['game_id'])
    op.create_index('ix_mlb_bullpens_team_id', 'mlb_bullpens', ['team_id'])


def downgrade() -> None:
    op.drop_table('mlb_bullpens')
    op.drop_table('mlb_pitchers')
    op.drop_table('sport_odds')
    op.drop_table('sport_teams')
    op.drop_table('sport_events')
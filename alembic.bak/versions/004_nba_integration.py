"""Phase 2 NBA Database Integration

Extend multi-sport schema for NBA
Uses existing SportEvent table, adds NBA-specific tables
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '004_nba_integration'
down_revision: Union[str, None] = '003_intelligence_maturation'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. NBA Team Stats snapshot table
    op.create_table(
        'nba_team_stats',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('team_id', sa.Integer(), nullable=False, index=True),
        sa.Column('team_name', sa.String(100)),
        sa.Column('team_code', sa.String(10)),
        sa.Column('season', sa.Integer(), nullable=False, index=True),
        
        # Record
        sa.Column('wins', sa.Integer(), default=0),
        sa.Column('losses', sa.Integer(), default=0),
        sa.Column('win_pct', sa.Float(), default=0),
        
        # Home/Away
        sa.Column('wins_home', sa.Integer(), default=0),
        sa.Column('losses_home', sa.Integer(), default=0),
        sa.Column('wins_away', sa.Integer(), default=0),
        sa.Column('losses_away', sa.Integer(), default=0),
        
        # Points
        sa.Column('points_for', sa.Integer(), default=0),
        sa.Column('points_against', sa.Integer(), default=0),
        sa.Column('points_for_avg', sa.Float(), default=0),
        sa.Column('points_against_avg', sa.Float(), default=0),
        
        # Streak
        sa.Column('streak', sa.String(20)),
        sa.Column('last_10_wins', sa.Integer(), default=0),
        
        # Conference/Division
        sa.Column('conference', sa.String(50)),
        sa.Column('division', sa.String(50)),
        sa.Column('conference_rank', sa.Integer()),
        sa.Column('division_rank', sa.Integer()),
        
        sa.Column('recorded_at', sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_nba_team_stats_composite', 'nba_team_stats', ['team_id', 'season'])
    
    # 2. NBA Player Stats snapshot table
    op.create_table(
        'nba_player_stats',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False, index=True),
        sa.Column('player_name', sa.String(100)),
        sa.Column('team_id', sa.Integer(), index=True),
        sa.Column('season', sa.Integer(), nullable=False, index=True),
        
        # Games
        sa.Column('games_played', sa.Integer(), default=0),
        sa.Column('games_started', sa.Integer(), default=0),
        sa.Column('minutes_avg', sa.Float(), default=0),
        
        # Shooting
        sa.Column('points_avg', sa.Float(), default=0),
        sa.Column('fgm_avg', sa.Float(), default=0),
        sa.Column('fga_avg', sa.Float(), default=0),
        sa.Column('fgp', sa.Float(), default=0),  # Field goal %
        sa.Column('three_pm_avg', sa.Float(), default=0),  # 3-pointers made
        sa.Column('three_pa_avg', sa.Float(), default=0),
        sa.Column('three_p_pct', sa.Float(), default=0),
        sa.Column('ftm_avg', sa.Float(), default=0),
        sa.Column('fta_avg', sa.Float(), default=0),
        sa.Column('ft_pct', sa.Float(), default=0),
        
        # Rebounds
        sa.Column('reb_avg', sa.Float(), default=0),
        sa.Column('off_reb_avg', sa.Float(), default=0),
        sa.Column('def_reb_avg', sa.Float(), default=0),
        
        # Other
        sa.Column('ast_avg', sa.Float(), default=0),
        sa.Column('stl_avg', sa.Float(), default=0),
        sa.Column('blk_avg', sa.Float(), default=0),
        sa.Column('turnovers_avg', sa.Float(), default=0),
        sa.Column('pf_avg', sa.Float(), default=0),  # Personal fouls
        
        # Advanced
        sa.Column('plus_minus_avg', sa.Float(), default=0),
        sa.Column('pir_avg', sa.Float(), default=0),  # Performance Index Rating
        
        sa.Column('recorded_at', sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_nba_player_stats_composite', 'nba_player_stats', ['player_id', 'season'])
    
    # 3. NBA Game Stats (per-game stats for model training)
    op.create_table(
        'nba_game_stats',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.Integer(), nullable=False, index=True),
        sa.Column('team_id', sa.Integer(), nullable=False, index=True),
        sa.Column('season', sa.Integer(), nullable=False),
        sa.Column('game_date', sa.DateTime(), nullable=False),
        
        # Is home
        sa.Column('is_home', sa.Boolean(), default=True),
        
        # Result
        sa.Column('won', sa.Boolean()),
        sa.Column('points', sa.Integer()),
        sa.Column('opp_points', sa.Integer()),
        
        # Pace factors
        sa.Column('possessions', sa.Float()),
        sa.Column('pace', sa.Float()),
        
        # Four factors
        sa.Column('efg_pct', sa.Float()),
        sa.Column('turnover_pct', sa.Float()),
        sa.Column('off_reb_pct', sa.Float()),
        sa.Column('fta_rate', sa.Float()),
        
        # Shooting
        sa.Column('three_p_attempts', sa.Integer()),
        sa.Column('three_p_made', sa.Integer()),
        sa.Column('free_throws_attempts', sa.Integer()),
        sa.Column('free_throws_made', sa.Integer()),
        
        sa.Column('recorded_at', sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_nba_game_stats_event', 'nba_game_stats', ['event_id', 'team_id'])
    
    # 4. NBA Injuries tracking (extend existing injuries table conceptually)
    op.create_table(
        'nba_injuries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False, index=True),
        sa.Column('player_name', sa.String(100)),
        sa.Column('team_id', sa.Integer(), index=True),
        sa.Column('status', sa.String(50)),  # day-to-day, out, doubtful
        sa.Column('description', sa.Text()),
        sa.Column('return_date', sa.DateTime()),
        sa.Column('start_date', sa.DateTime()),
        sa.Column('is_key_player', sa.Boolean(), default=False),
        sa.Column('severity_impact', sa.Float(), default=0.5),  # 0-1 impact on win probability
        sa.Column('fetched_at', sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_nba_injuries_player', 'nba_injuries', ['player_id', 'fetched_at'])
    
    # 5. NBA NBA-specific prediction records (extends prediction_records)
    op.create_table(
        'nba_predictions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('prediction_record_id', sa.Integer(), nullable=False, index=True),
        sa.Column('fixture_id', sa.Integer(), nullable=False, index=True),
        sa.Column('model_version_id', sa.Integer()),
        
        # Model output
        sa.Column('home_win_prob', sa.Float(), nullable=False),
        sa.Column('away_win_prob', sa.Float(), nullable=False),
        sa.Column('predicted_winner', sa.String(10)),  # 'home' or 'away'
        
        # Market
        sa.Column('market_home_odds', sa.Float()),
        sa.Column('market_away_odds', sa.Float()),
        sa.Column('spread_home', sa.Float()),
        sa.Column('spread_away', sa.Float()),
        sa.Column('total_points', sa.Float()),
        
        # EV calculation
        sa.Column('home_edge', sa.Float()),
        sa.Column('away_edge', sa.Float()),
        sa.Column('home_ev', sa.Float()),
        sa.Column('away_ev', sa.Float()),
        
        # Decision
        sa.Column('bet_decision', sa.String(10)),  # 'home', 'away', 'pass'
        sa.Column('bet_odds', sa.Float()),
        sa.Column('stake_fraction', sa.Float()),
        
        # Lineup impact
        sa.Column('home_key_missing', sa.Integer(), default=0),
        sa.Column('away_key_missing', sa.Integer(), default=0),
        sa.Column('lineup_impact', sa.Float(), default=0),
        
        sa.Column('predicted_at', sa.DateTime(), default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_nba_pred_fixture', 'nba_predictions', ['fixture_id'])


def downgrade() -> None:
    op.drop_table('nba_predictions')
    op.drop_table('nba_injuries')
    op.drop_table('nba_game_stats')
    op.drop_table('nba_player_stats')
    op.drop_table('nba_team_stats')
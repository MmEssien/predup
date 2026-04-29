"""Phase 4 - Intelligence Maturation Database Migration

Adds tables for:
1. Injury tracking
2. Suspension tracking
3. Settlement records with CLV and calibration drift
4. Lineup confirmations
5. Health report history
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision: str = '003_intelligence_maturation'
down_revision: Union[str, None] = '002_multi_sport'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. INJURIES TABLE - Track player injuries
    op.create_table(
        'injuries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('external_id', sa.String(50), unique=True, nullable=False, index=True),
        sa.Column('player_id', sa.Integer(), sa.ForeignKey('players.id'), index=True),
        sa.Column('fixture_id', sa.Integer(), sa.ForeignKey('fixtures.id'), index=True),
        sa.Column('team_id', sa.Integer(), sa.ForeignKey('teams.id'), index=True),
        sa.Column('type', sa.String(50), nullable=False),  # muscle, knock, illness, etc
        sa.Column('severity', sa.Float(), nullable=False),  # 0.0 - 1.0
        sa.Column('status', sa.String(20), nullable=False, default='active'),  # active, returned, chronic
        sa.Column('description', sa.Text()),
        sa.Column('expected_return', sa.DateTime()),
        sa.Column('actual_return', sa.DateTime()),
        sa.Column('fetched_at', sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_injuries_player_fixture', 'injuries', ['player_id', 'fixture_id'])
    op.create_index('ix_injuries_team_match_date', 'injuries', ['team_id', 'fetched_at'])
    
    # 2. SUSPENSIONS TABLE - Track player suspensions
    op.create_table(
        'suspensions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('external_id', sa.String(50), unique=True, nullable=False, index=True),
        sa.Column('player_id', sa.Integer(), sa.ForeignKey('players.id'), index=True),
        sa.Column('fixture_id', sa.Integer(), sa.ForeignKey('fixtures.id'), index=True),
        sa.Column('team_id', sa.Integer(), sa.ForeignKey('teams.id'), index=True),
        sa.Column('reason', sa.String(255)),  # 2nd yellow, red card, disciplinary
        sa.Column('matches_remaining', sa.Integer(), default=0),
        sa.Column('is_serving', sa.Boolean(), default=True),
        sa.Column('start_date', sa.DateTime()),
        sa.Column('end_date', sa.DateTime()),
        sa.Column('fetched_at', sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_suspensions_player_fixture', 'suspensions', ['player_id', 'fixture_id'])
    
    # 3. LINEUPS TABLE - Store confirmed lineups
    op.create_table(
        'lineups',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fixture_id', sa.Integer(), sa.ForeignKey('fixtures.id'), nullable=False, index=True),
        sa.Column('team_id', sa.Integer(), sa.ForeignKey('teams.id'), nullable=False, index=True),
        sa.Column('formation', sa.String(10)),
        sa.Column('players_json', sa.Text()),  # JSON array of player IDs
        sa.Column('confirmed', sa.Boolean(), default=False),
        sa.Column('fetched_at', sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.UniqueConstraint('fixture_id', 'team_id', name='uq_lineup_fixture_team'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # 4. SETTLED PREDICTIONS - Enhanced tracking
    op.create_table(
        'settled_predictions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('prediction_record_id', sa.Integer(), sa.ForeignKey('prediction_records.id'), nullable=False, index=True),
        sa.Column('fixture_id', sa.Integer(), sa.ForeignKey('fixtures.id'), nullable=False, index=True),
        
        # Outcome
        sa.Column('actual_value', sa.Integer(), nullable=False),
        sa.Column('actual_score', sa.String(20)),  # "2-1" format
        
        # CLV metrics
        sa.Column('closing_odds', sa.Float()),
        sa.Column('closing_implied', sa.Float()),
        sa.Column('clv', sa.Float()),  # closing_line_value = predicted_prob - closing_implied
        sa.Column('clv_percentage', sa.Float()),
        
        # Calibration drift
        sa.Column('calibration_drift', sa.Float()),  # actual - predicted (positive = under-confident)
        
        # Profit tracking
        sa.Column('predicted_outcome', sa.String(10)),
        sa.Column('actual_outcome', sa.String(10)),
        sa.Column('is_correct', sa.Boolean()),
        sa.Column('stake', sa.Float(), nullable=False, default=0),
        sa.Column('odds', sa.Float(), nullable=False),
        sa.Column('profit', sa.Float(), default=0),
        
        # Metadata
        sa.Column('settled_at', sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.Column('source', sa.String(20), default='auto'),  # auto, manual, api
        sa.Column('notes', sa.Text()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_settled_fixture', 'settled_predictions', ['fixture_id'])
    op.create_index('ix_settled_correct', 'settled_predictions', ['is_correct'])
    op.create_index('ix_settled_clv', 'settled_predictions', ['clv'])
    
    # 5. MODEL HEALTH REPORTS - Weekly reports
    op.create_table(
        'model_health_reports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('report_date', sa.DateTime(), nullable=False, index=True),
        sa.Column('period_start', sa.DateTime(), nullable=False),
        sa.Column('period_end', sa.DateTime(), nullable=False),
        
        # ROI by league
        sa.Column('bl1_roi', sa.Float()),
        sa.Column('bl1_bets', sa.Integer()),
        sa.Column('bl1_win_rate', sa.Float()),
        sa.Column('pl_roi', sa.Float()),
        sa.Column('pl_bets', sa.Integer()),
        sa.Column('pl_win_rate', sa.Float()),
        sa.Column('other_roi', sa.Float()),
        sa.Column('other_bets', sa.Integer()),
        
        # Threshold performance
        sa.Column('threshold_070_wins', sa.Integer()),
        sa.Column('threshold_070_total', sa.Integer()),
        sa.Column('threshold_055_wins', sa.Integer()),
        sa.Column('threshold_055_total', sa.Integer()),
        
        # Calibration
        sa.Column('calibration_ece', sa.Float()),  # Expected Calibration Error
        sa.Column('calibration_mce', sa.Float()),  # Max Calibration Error
        sa.Column('calibration_drift', sa.Float()),
        
        # Drawdown
        sa.Column('peak_bankroll', sa.Float()),
        sa.Column('current_bankroll', sa.Float()),
        sa.Column('max_drawdown', sa.Float()),
        sa.Column('max_drawdown_pct', sa.Float()),
        
        # Recommendations
        sa.Column('recommendation', sa.String(50)),  # CONTINUE, RETUNE, INVESTIGATE
        sa.Column('recommendation_reason', sa.Text()),
        sa.Column('parameters_changed', sa.Text()),  # JSON
        
        sa.Column('created_at', sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    
    # 6. Add league_code column and indexes to prediction_records
    try:
        op.add_column('prediction_records', sa.Column('league_code', sa.String(20)))
    except:
        pass  # Column may already exist
    op.create_index('ix_pred_record_league', 'prediction_records', ['league_code'])
    op.create_index('ix_pred_record_settled', 'prediction_records', ['settled_at'])


def downgrade() -> None:
    op.drop_table('model_health_reports')
    op.drop_table('settled_predictions')
    op.drop_table('lineups')
    op.drop_table('suspensions')
    op.drop_table('injuries')
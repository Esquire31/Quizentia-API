"""add selected_questions and backup_questions

Revision ID: add_question_selection
Revises: 88df478f4e71
Create Date: 2026-01-15

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_question_selection'
down_revision = '88df478f4e71'
branch_labels = None
depends_on = None


def upgrade():
    # Add selected_questions to quiz_definition if not exists
    from sqlalchemy import inspect
    from alembic import op
    
    conn = op.get_bind()
    inspector = inspect(conn)
    
    # Check if selected_questions column exists
    columns = [col['name'] for col in inspector.get_columns('quiz_definition')]
    if 'selected_questions' not in columns:
        op.add_column('quiz_definition', 
            sa.Column('selected_questions', sa.Text(), nullable=True))
    
    # Check if backup_questions table exists
    tables = inspector.get_table_names()
    if 'backup_questions' not in tables:
        # Create backup_questions table
        op.create_table(
            'backup_questions',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('quiz_id', sa.Integer(), nullable=False),
            sa.Column('question_index', sa.Integer(), nullable=False),
            sa.Column('week_id', sa.String(100), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
            sa.ForeignKeyConstraint(['quiz_id'], ['quizzes.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_backup_questions_week_id', 'backup_questions', ['week_id'])


def downgrade():
    op.drop_index('ix_backup_questions_week_id', table_name='backup_questions')
    op.drop_table('backup_questions')
    op.drop_column('quiz_definition', 'selected_questions')

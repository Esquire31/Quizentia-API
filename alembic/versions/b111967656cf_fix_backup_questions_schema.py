"""fix_backup_questions_schema

Revision ID: b111967656cf
Revises: b0e7b1b833a3
Create Date: 2026-01-16 03:30:23.460209

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
import json


# revision identifiers, used by Alembic.
revision: str = 'b111967656cf'
down_revision: Union[str, Sequence[str], None] = 'b0e7b1b833a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Transform backup_questions from old schema (individual questions) 
    to new schema (one row per quiz with all indices).
    """
    conn = op.get_bind()
    
    # 1. Check if backup_questions has old schema
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('backup_questions')]
    
    if 'question_index' in columns and 'question_indices' not in columns:
        print("Migrating backup_questions from old to new schema...")
        
        # Get all backup questions from old schema
        old_backup = conn.execute(text("""
            SELECT quiz_id, question_index 
            FROM backup_questions
            ORDER BY quiz_id, question_index
        """)).fetchall()
        
        # Group by quiz_id
        backup_by_quiz = {}
        for quiz_id, question_index in old_backup:
            if quiz_id not in backup_by_quiz:
                backup_by_quiz[quiz_id] = []
            backup_by_quiz[quiz_id].append(question_index)
        
        print(f"Found {len(old_backup)} individual backup questions from {len(backup_by_quiz)} quizzes")
        
        # Drop old table and create new one
        op.drop_table('backup_questions')
        
        op.create_table(
            'backup_questions',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('quiz_id', sa.Integer(), nullable=False),
            sa.Column('question_indices', sa.Text(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(['quiz_id'], ['quizzes.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('quiz_id', name='uq_backup_quiz_id')
        )
        
        # Insert aggregated data
        for quiz_id, indices in backup_by_quiz.items():
            conn.execute(text("""
                INSERT INTO backup_questions (quiz_id, question_indices, created_at)
                VALUES (:quiz_id, :question_indices, NOW())
            """), {
                'quiz_id': quiz_id,
                'question_indices': json.dumps(indices)
            })
        
        print(f"Migrated to new schema: {len(backup_by_quiz)} quiz entries")
    else:
        print("backup_questions already has new schema or columns are different")
    
    # 2. Ensure week_questions and week_summary exist with correct schema
    tables = inspector.get_table_names()
    
    if 'week_questions' not in tables:
        print("Creating week_questions table...")
        op.create_table(
            'week_questions',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('week_id', sa.String(100), nullable=False),
            sa.Column('quiz_id', sa.Integer(), nullable=False),
            sa.Column('selected_indices', sa.Text(), nullable=False),
            sa.Column('unselected_indices', sa.Text(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(['quiz_id'], ['quizzes.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('week_id', 'quiz_id', name='uq_week_quiz')
        )
    
    if 'week_summary' not in tables:
        print("Creating week_summary table...")
        op.create_table(
            'week_summary',
            sa.Column('week_id', sa.String(100), nullable=False),
            sa.Column('total_selected', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('total_unselected', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('total_quizzes', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('last_updated', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.PrimaryKeyConstraint('week_id')
        )
    
    print("Schema migration complete!")


def downgrade() -> None:
    """Downgrade back to old schema."""
    conn = op.get_bind()
    
    # Get current backup questions
    backup_qs = conn.execute(text("""
        SELECT id, quiz_id, question_indices 
        FROM backup_questions
    """)).fetchall()
    
    # Drop new table
    op.drop_table('backup_questions')
    
    # Create old table
    op.create_table(
        'backup_questions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('quiz_id', sa.Integer(), nullable=False),
        sa.Column('question_index', sa.Integer(), nullable=False),
        sa.Column('week_id', sa.String(100)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['quiz_id'], ['quizzes.id']),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Insert individual questions
    for backup_id, quiz_id, question_indices_json in backup_qs:
        indices = json.loads(question_indices_json)
        for idx in indices:
            conn.execute(text("""
                INSERT INTO backup_questions (quiz_id, question_index, created_at)
                VALUES (:quiz_id, :question_index, NOW())
            """), {
                'quiz_id': quiz_id,
                'question_index': idx
            })


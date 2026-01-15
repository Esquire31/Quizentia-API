"""migrate_to_new_schema_week_questions_backup_questions

Revision ID: b0e7b1b833a3
Revises: add_question_selection
Create Date: 2026-01-16 03:13:03.600844

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
import json


# revision identifiers, used by Alembic.
revision: str = 'b0e7b1b833a3'
down_revision: Union[str, Sequence[str], None] = 'add_question_selection'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to new design."""
    
    conn = op.get_bind()
    
    # 1. Create new tables (check if they exist first)
    try:
        op.create_table(
            'week_questions',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('week_id', sa.String(100), nullable=False, index=True),
            sa.Column('quiz_id', sa.Integer(), nullable=False),
            sa.Column('selected_indices', sa.Text(), nullable=False),
            sa.Column('unselected_indices', sa.Text(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(['quiz_id'], ['quizzes.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('week_id', 'quiz_id', name='uq_week_quiz')
        )
        print("Created week_questions table")
    except Exception as e:
        print(f"week_questions table already exists or error: {e}")
    
    try:
        op.create_table(
            'backup_questions',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('quiz_id', sa.Integer(), nullable=False, unique=True),
            sa.Column('question_indices', sa.Text(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(['quiz_id'], ['quizzes.id']),
            sa.PrimaryKeyConstraint('id')
        )
        print("Created backup_questions table")
    except Exception as e:
        print(f"backup_questions table already exists or error: {e}")
    
    try:
        op.create_table(
            'week_summary',
            sa.Column('week_id', sa.String(100), nullable=False),
            sa.Column('total_selected', sa.Integer(), nullable=False, default=0),
            sa.Column('total_unselected', sa.Integer(), nullable=False, default=0),
            sa.Column('total_quizzes', sa.Integer(), nullable=False, default=0),
            sa.Column('last_updated', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.PrimaryKeyConstraint('week_id')
        )
        print("Created week_summary table")
    except Exception as e:
        print(f"week_summary table already exists or error: {e}")
    
    # Get all quiz definitions
    quiz_defs = conn.execute(text("""
        SELECT id, quiz_id, week_id, selected_questions 
        FROM quiz_definition
    """)).fetchall()
    
    # Get all quizzes to know total question count
    quizzes = conn.execute(text("""
        SELECT id, questions FROM quizzes
    """)).fetchall()
    
    quiz_question_counts = {}
    for quiz in quizzes:
        quiz_id = quiz[0]
        questions_json = quiz[1]
        questions = json.loads(questions_json)
        quiz_question_counts[quiz_id] = len(questions)
    
    # Migrate each quiz definition
    for qd in quiz_defs:
        qd_id, quiz_id, week_id, selected_questions_json = qd
        
        if quiz_id not in quiz_question_counts:
            continue
        
        total_questions = quiz_question_counts[quiz_id]
        all_indices = list(range(total_questions))
        
        # Parse selected indices
        if selected_questions_json:
            selected_indices = json.loads(selected_questions_json)
        else:
            selected_indices = all_indices  # Default: all selected
        
        # Calculate unselected
        unselected_indices = [i for i in all_indices if i not in selected_indices]
        
        # Insert into week_questions
        conn.execute(text("""
            INSERT INTO week_questions (week_id, quiz_id, selected_indices, unselected_indices, created_at)
            VALUES (:week_id, :quiz_id, :selected_indices, :unselected_indices, NOW())
        """), {
            'week_id': week_id,
            'quiz_id': quiz_id,
            'selected_indices': json.dumps(selected_indices),
            'unselected_indices': json.dumps(unselected_indices)
        })
    
    # 3. Migrate backup_questions_old to backup_questions (aggregate by quiz_id)
    # First, rename old backup_questions table
    op.rename_table('backup_questions', 'backup_questions_old')
    
    # Get all backup questions and aggregate by quiz_id
    backup_qs = conn.execute(text("""
        SELECT quiz_id, question_index 
        FROM backup_questions_old
        ORDER BY quiz_id, question_index
    """)).fetchall()
    
    # Group by quiz_id
    backup_by_quiz = {}
    for bq in backup_qs:
        quiz_id, question_index = bq
        if quiz_id not in backup_by_quiz:
            backup_by_quiz[quiz_id] = []
        backup_by_quiz[quiz_id].append(question_index)
    
    # Insert aggregated backup questions
    for quiz_id, indices in backup_by_quiz.items():
        conn.execute(text("""
            INSERT INTO backup_questions (quiz_id, question_indices, created_at)
            VALUES (:quiz_id, :question_indices, NOW())
        """), {
            'quiz_id': quiz_id,
            'question_indices': json.dumps(indices)
        })
    
    # 4. Build week_summary
    week_data = {}
    for qd in quiz_defs:
        qd_id, quiz_id, week_id, selected_questions_json = qd
        
        if quiz_id not in quiz_question_counts:
            continue
        
        if week_id not in week_data:
            week_data[week_id] = {
                'total_selected': 0,
                'total_unselected': 0,
                'total_quizzes': 0
            }
        
        total_questions = quiz_question_counts[quiz_id]
        if selected_questions_json:
            selected_count = len(json.loads(selected_questions_json))
        else:
            selected_count = total_questions
        
        unselected_count = total_questions - selected_count
        
        week_data[week_id]['total_selected'] += selected_count
        week_data[week_id]['total_unselected'] += unselected_count
        week_data[week_id]['total_quizzes'] += 1
    
    # Insert week summaries
    for week_id, data in week_data.items():
        conn.execute(text("""
            INSERT INTO week_summary (week_id, total_selected, total_unselected, total_quizzes, last_updated)
            VALUES (:week_id, :total_selected, :total_unselected, :total_quizzes, NOW())
        """), {
            'week_id': week_id,
            'total_selected': data['total_selected'],
            'total_unselected': data['total_unselected'],
            'total_quizzes': data['total_quizzes']
        })
    
    # 5. Add unique constraint to quizzes.url
    try:
        op.create_unique_constraint('uq_quiz_url', 'quizzes', ['url'])
    except:
        pass  # Constraint might already exist or have duplicate data
    
    print("Migration completed successfully!")
    print(f"- Migrated {len(quiz_defs)} quiz definitions to week_questions")
    print(f"- Migrated {len(backup_by_quiz)} backup quizzes")
    print(f"- Created {len(week_data)} week summaries")


def downgrade() -> None:
    """Downgrade schema back to old design."""
    
    # Restore backup_questions_old to backup_questions
    op.rename_table('backup_questions_old', 'backup_questions')
    
    # Drop new tables
    op.drop_table('week_summary')
    op.drop_table('backup_questions')
    op.drop_table('week_questions')
    
    # Remove unique constraint from quizzes.url
    try:
        op.drop_constraint('uq_quiz_url', 'quizzes', type_='unique')
    except:
        pass


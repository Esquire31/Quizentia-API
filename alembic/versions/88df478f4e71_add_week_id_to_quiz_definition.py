"""Add week_id to quiz_definition

Revision ID: 88df478f4e71
Revises: 0001
Create Date: 2026-01-01 20:18:01.076109

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '88df478f4e71'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add week_id column to quiz_definition table
    op.add_column('quiz_definition', sa.Column('week_id', sa.String(length=100), nullable=True))
    op.create_index(op.f('ix_quiz_definition_week_id'), 'quiz_definition', ['week_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Remove week_id column from quiz_definition table
    op.drop_index(op.f('ix_quiz_definition_week_id'), table_name='quiz_definition')
    op.drop_column('quiz_definition', 'week_id')

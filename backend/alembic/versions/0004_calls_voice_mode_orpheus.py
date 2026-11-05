"""calls.voice_mode allows orpheus

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-05 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint(op.f('ck_calls_voice_mode'), 'calls', type_='check')
    op.create_check_constraint(
        op.f('ck_calls_voice_mode'), 'calls', "voice_mode IN ('kokoro', 'lite', 'orpheus')"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("UPDATE calls SET voice_mode = 'lite' WHERE voice_mode = 'orpheus'")
    op.drop_constraint(op.f('ck_calls_voice_mode'), 'calls', type_='check')
    op.create_check_constraint(
        op.f('ck_calls_voice_mode'), 'calls', "voice_mode IN ('kokoro', 'lite')"
    )

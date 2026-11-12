"""conferencia sem o texto lido

Revision ID: a3c51e7d9b20
Revises: f1af0e0525dd
Create Date: 2026-11-12 02:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3c51e7d9b20'
down_revision: Union[str, Sequence[str], None] = 'f1af0e0525dd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('leitura_pagina', schema=None) as batch_op:
        batch_op.add_column(sa.Column('conferida_sem_texto', sa.Boolean(), server_default='0', nullable=False))


def downgrade() -> None:
    with op.batch_alter_table('leitura_pagina', schema=None) as batch_op:
        batch_op.drop_column('conferida_sem_texto')

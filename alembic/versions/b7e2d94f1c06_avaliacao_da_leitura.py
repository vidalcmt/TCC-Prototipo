"""avaliacao da leitura

Revision ID: b7e2d94f1c06
Revises: a3c51e7d9b20
Create Date: 2026-11-12 03:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7e2d94f1c06'
down_revision: Union[str, Sequence[str], None] = 'a3c51e7d9b20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('avaliacao_leitura',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('leitura_pagina_id', sa.Integer(), nullable=True),
    sa.Column('folha_id', sa.Integer(), nullable=False),
    sa.Column('campo', sa.String(length=40), nullable=False),
    sa.Column('nota', sa.String(length=20), nullable=False),
    sa.Column('corrigiu_erro_aluno', sa.Boolean(), nullable=False),
    sa.Column('texto_lido', sa.Text(), nullable=False),
    sa.Column('texto_ocr', sa.Text(), nullable=True),
    sa.Column('servico_ocr', sa.String(length=50), nullable=True),
    sa.Column('com_revisao', sa.Boolean(), nullable=False),
    sa.Column('trocas', sa.Integer(), nullable=False),
    sa.Column('usuario_id', sa.Integer(), nullable=True),
    sa.Column('criado_em', sa.DateTime(timezone=True), nullable=False),
    sa.Column('atualizado_em', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['folha_id'], ['folha.id'], name='fk_avaliacao_leitura_folha'),
    sa.ForeignKeyConstraint(['leitura_pagina_id'], ['leitura_pagina.id'], name='fk_avaliacao_leitura_leitura',
                            ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id'], name='fk_avaliacao_leitura_usuario'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('leitura_pagina_id', 'campo', name='uq_avaliacao_leitura_campo')
    )


def downgrade() -> None:
    op.drop_table('avaliacao_leitura')

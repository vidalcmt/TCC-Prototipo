"""origem das metricas

Revision ID: be27d4f7f58d
Revises: 4820600e6f6c
Create Date: 2026-10-24 16:00:14.042647

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'be27d4f7f58d'
down_revision: Union[str, Sequence[str], None] = '4820600e6f6c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Liga cada métrica à questão e à resposta de origem.

    As chamadas antigas que geraram correção recebem a origem a partir da
    correção. As falhas antigas ficam sem origem, porque ela não foi gravada.
    """
    with op.batch_alter_table('metrica_requisicao', schema=None) as batch_op:
        batch_op.add_column(sa.Column('questao_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('submissao_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_metrica_requisicao_questao', 'questao', ['questao_id'], ['id'])
        batch_op.create_foreign_key('fk_metrica_requisicao_submissao', 'submissao', ['submissao_id'], ['id'])

    op.execute(
        "UPDATE metrica_requisicao SET "
        "questao_id = (SELECT questao_id FROM correcao WHERE correcao.id = metrica_requisicao.correcao_id), "
        "submissao_id = (SELECT submissao_id FROM correcao WHERE correcao.id = metrica_requisicao.correcao_id) "
        "WHERE correcao_id IS NOT NULL"
    )


def downgrade() -> None:
    with op.batch_alter_table('metrica_requisicao', schema=None) as batch_op:
        batch_op.drop_constraint('fk_metrica_requisicao_submissao', type_='foreignkey')
        batch_op.drop_constraint('fk_metrica_requisicao_questao', type_='foreignkey')
        batch_op.drop_column('submissao_id')
        batch_op.drop_column('questao_id')

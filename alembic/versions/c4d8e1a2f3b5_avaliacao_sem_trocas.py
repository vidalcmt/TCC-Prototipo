"""avaliacao da leitura sem o veredito por troca

Revision ID: c4d8e1a2f3b5
Revises: b7e2d94f1c06
Create Date: 2026-11-12 16:40:00

A primeira versão da migração b7e2d94f1c06 criou a coluna trocas_json (o
veredito de cada troca da IA), obrigatória e sem valor padrão. Essa avaliação
troca por troca foi retirada, e a migração voltou a não ter a coluna, mas um
banco que já tinha rodado a primeira versão ficou com ela: cada avaliação nova
falhava ao gravar, porque o sistema não preenche mais a coluna. Esta migração
retira a coluna onde ela existir e não faz nada nos outros bancos.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4d8e1a2f3b5'
down_revision: Union[str, Sequence[str], None] = 'b7e2d94f1c06'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _colunas() -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("avaliacao_leitura")}


def upgrade() -> None:
    if "trocas_json" in _colunas():
        with op.batch_alter_table('avaliacao_leitura', schema=None) as batch_op:
            batch_op.drop_column('trocas_json')
    # A coluna nota fica como estiver: na primeira versão ela aceitava vazio, e uma avaliação feita só
    # por trocas, nesse intervalo, não pode ser perdida por isso.


def downgrade() -> None:
    pass  # a coluna retirada não é usada pelo sistema

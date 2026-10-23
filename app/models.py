"""Tabelas do banco, conforme a seção "Arquitetura e modelo de dados" da especificação.

Duas tabelas existem por razão metodológica e não devem ser simplificadas:
- revisao_professor guarda a nota sugerida e a final lado a lado, o que permite
  calcular a taxa de concordância entre o modelo e o professor;
- metrica_requisicao registra também as requisições que falharam, porque a taxa
  de falha é um resultado da pesquisa.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def agora() -> datetime:
    return datetime.now(timezone.utc)


class Usuario(Base):
    """Conta de acesso. Criada pelo administrador; não há cadastro aberto."""

    __tablename__ = "usuario"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(200), unique=True)
    senha_resumo: Mapped[str] = mapped_column(String(200))
    papel: Mapped[str] = mapped_column(String(20), default="avaliador")  # "admin" ou "avaliador"
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    precisa_trocar_senha: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    ultimo_acesso: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def eh_admin(self) -> bool:
        return self.papel == "admin"


class Questao(Base):
    __tablename__ = "questao"

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(20))  # "objetiva" ou "discursiva"
    enunciado: Mapped[str] = mapped_column(Text)
    area: Mapped[str | None] = mapped_column(String(100))
    fonte: Mapped[str | None] = mapped_column(String(200))  # ex.: "ENEM"
    ano: Mapped[int | None] = mapped_column(Integer)
    nota_maxima: Mapped[float] = mapped_column(Float, default=10.0)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)

    alternativas: Mapped[list["Alternativa"]] = relationship(
        back_populates="questao", cascade="all, delete-orphan", order_by="Alternativa.letra"
    )
    criterios: Mapped[list["CriterioRubrica"]] = relationship(
        back_populates="questao", cascade="all, delete-orphan", order_by="CriterioRubrica.id"
    )
    # Itens de uma discursiva (a, b, c...), como nas provas da Fuvest. Vazio
    # quando a questão tem uma resposta única.
    itens: Mapped[list["ItemQuestao"]] = relationship(
        back_populates="questao", cascade="all, delete-orphan", order_by="ItemQuestao.letra"
    )
    resposta_esperada: Mapped["RespostaEsperada | None"] = relationship(
        back_populates="questao", cascade="all, delete-orphan", uselist=False
    )


class Alternativa(Base):
    __tablename__ = "alternativa"

    id: Mapped[int] = mapped_column(primary_key=True)
    questao_id: Mapped[int] = mapped_column(ForeignKey("questao.id"))
    letra: Mapped[str] = mapped_column(String(1))
    texto: Mapped[str] = mapped_column(Text)
    correta: Mapped[bool] = mapped_column(Boolean, default=False)

    questao: Mapped[Questao] = relationship(back_populates="alternativas")


class ItemQuestao(Base):
    """Um item de uma questão discursiva, com o seu próprio comando."""

    __tablename__ = "item_questao"
    __table_args__ = (UniqueConstraint("questao_id", "letra", name="uq_item_questao_letra"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    questao_id: Mapped[int] = mapped_column(ForeignKey("questao.id"))
    letra: Mapped[str] = mapped_column(String(1))
    enunciado: Mapped[str] = mapped_column(Text)

    questao: Mapped[Questao] = relationship(back_populates="itens")


class CriterioRubrica(Base):
    """Opcional: a questão discursiva pode ou não ter rubrica (RF04)."""

    __tablename__ = "criterio_rubrica"

    id: Mapped[int] = mapped_column(primary_key=True)
    questao_id: Mapped[int] = mapped_column(ForeignKey("questao.id"))
    # Item a que o critério se refere. Vazio em questão sem itens ou em
    # critério que vale para a resposta inteira.
    item_id: Mapped[int | None] = mapped_column(ForeignKey("item_questao.id"))
    descricao: Mapped[str] = mapped_column(Text)
    peso: Mapped[float] = mapped_column(Float, default=1.0)

    questao: Mapped[Questao] = relationship(back_populates="criterios")
    item: Mapped["ItemQuestao | None"] = relationship()


class RespostaEsperada(Base):
    """Opcional: rodar com e sem ela é uma das condições experimentais (RF08)."""

    __tablename__ = "resposta_esperada"

    questao_id: Mapped[int] = mapped_column(ForeignKey("questao.id"), primary_key=True)
    texto: Mapped[str] = mapped_column(Text)

    questao: Mapped[Questao] = relationship(back_populates="resposta_esperada")


class Submissao(Base):
    __tablename__ = "submissao"

    id: Mapped[int] = mapped_column(primary_key=True)
    questao_id: Mapped[int] = mapped_column(ForeignKey("questao.id"))
    resposta_aluno: Mapped[str | None] = mapped_column(Text)
    alternativa_escolhida: Mapped[str | None] = mapped_column(String(1))
    # Identificador anônimo da resposta no corpus (ex.: "R014") e sua origem
    # ("autor", "voluntario", "especialista"), usada como variável de análise.
    codigo_corpus: Mapped[str | None] = mapped_column(String(50))
    origem: Mapped[str | None] = mapped_column(String(30))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)

    # Em questão com itens, a resposta de cada item fica aqui, e resposta_aluno
    # guarda o texto completo, com os itens identificados pela letra.
    respostas_itens: Mapped[list["RespostaItem"]] = relationship(
        cascade="all, delete-orphan", order_by="RespostaItem.id"
    )

    def resposta_do_item(self, letra: str) -> str:
        for r in self.respostas_itens:
            if r.item.letra == letra:
                return r.texto
        return ""


class RespostaItem(Base):
    __tablename__ = "resposta_item"
    __table_args__ = (UniqueConstraint("submissao_id", "item_id", name="uq_resposta_item"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    submissao_id: Mapped[int] = mapped_column(ForeignKey("submissao.id"))
    item_id: Mapped[int] = mapped_column(ForeignKey("item_questao.id"))
    texto: Mapped[str] = mapped_column(Text, default="")  # vazio: item em branco

    item: Mapped[ItemQuestao] = relationship()


class Correcao(Base):
    __tablename__ = "correcao"

    id: Mapped[int] = mapped_column(primary_key=True)
    submissao_id: Mapped[int | None] = mapped_column(ForeignKey("submissao.id"))
    questao_id: Mapped[int] = mapped_column(ForeignKey("questao.id"))
    feedback_json: Mapped[str] = mapped_column(Text)
    nota_sugerida: Mapped[float | None] = mapped_column(Float)
    usou_resposta_esperada: Mapped[bool | None] = mapped_column(Boolean)
    modelo: Mapped[str] = mapped_column(String(100))
    prompt_versao: Mapped[str] = mapped_column(String(100))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class RevisaoProfessor(Base):
    """A nota final só existe aqui, depois da ação do professor (RF10 e RF11).

    Cada correção recebe no máximo uma revisão, e ela não é alterada depois:
    a decisão registrada é o dado da pesquisa.
    """

    __tablename__ = "revisao_professor"
    __table_args__ = (UniqueConstraint("correcao_id", name="uq_revisao_professor_correcao"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    correcao_id: Mapped[int] = mapped_column(ForeignKey("correcao.id"))
    # Quem decidiu. Vazio nas revisões feitas antes do login existir.
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    nota_sugerida: Mapped[float] = mapped_column(Float)
    nota_final: Mapped[float] = mapped_column(Float)
    aceitou_sugestao: Mapped[bool] = mapped_column(Boolean)
    comentario: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)


class MetricaRequisicao(Base):
    """Uma linha por chamada ao modelo, com sucesso ou falha (RF12).

    correcao_id fica vazio quando a chamada falha antes de gerar uma correção.
    """

    __tablename__ = "metrica_requisicao"

    id: Mapped[int] = mapped_column(primary_key=True)
    correcao_id: Mapped[int | None] = mapped_column(ForeignKey("correcao.id"))
    # Quem disparou a chamada; vazio em scripts e chamadas anteriores ao login.
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    tipo_questao: Mapped[str | None] = mapped_column(String(20))
    usou_resposta_esperada: Mapped[bool | None] = mapped_column(Boolean)
    modelo_solicitado: Mapped[str] = mapped_column(String(100))
    # Identificador devolvido pela API: é ele que registra a versão exata usada.
    modelo: Mapped[str | None] = mapped_column(String(100))
    prompt_versao: Mapped[str] = mapped_column(String(100))
    tokens_entrada: Mapped[int | None] = mapped_column(Integer)
    tokens_entrada_cache: Mapped[int | None] = mapped_column(Integer)
    tokens_escrita_cache: Mapped[int | None] = mapped_column(Integer)
    tokens_saida: Mapped[int | None] = mapped_column(Integer)
    tokens_raciocinio: Mapped[int | None] = mapped_column(Integer)
    custo_usd: Mapped[float | None] = mapped_column(Float)
    latencia_ms: Mapped[float] = mapped_column(Float)
    sucesso: Mapped[bool] = mapped_column(Boolean)
    motivo_falha: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)

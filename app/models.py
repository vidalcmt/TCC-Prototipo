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
    # Numa folha de respostas, cada questão tem no máximo uma resposta.
    __table_args__ = (UniqueConstraint("folha_id", "questao_id", name="uq_submissao_folha_questao"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    questao_id: Mapped[int] = mapped_column(ForeignKey("questao.id"))
    resposta_aluno: Mapped[str | None] = mapped_column(Text)
    # Objetivas: a letra marcada; vazio é em branco e "*" é mais de uma marcada.
    alternativa_escolhida: Mapped[str | None] = mapped_column(String(1))
    # Folha de respostas de onde veio a resposta; vazio nas respostas do corpus.
    folha_id: Mapped[int | None] = mapped_column(ForeignKey("folha.id", name="fk_submissao_folha"))
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
    folha: Mapped["Folha | None"] = relationship(back_populates="respostas")

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
    questao_id e submissao_id dizem de onde veio a chamada mesmo nas falhas,
    o que permite ligar cada custo à questão e à resposta que o geraram.
    """

    __tablename__ = "metrica_requisicao"

    id: Mapped[int] = mapped_column(primary_key=True)
    correcao_id: Mapped[int | None] = mapped_column(ForeignKey("correcao.id"))
    questao_id: Mapped[int | None] = mapped_column(ForeignKey("questao.id"))
    submissao_id: Mapped[int | None] = mapped_column(ForeignKey("submissao.id"))
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


class Atividade(Base):
    """Um conjunto de questões montado pelo professor para uma turma, que pode
    ser impresso em folha A4. Não interfere na correção nem nas métricas."""

    __tablename__ = "atividade"

    id: Mapped[int] = mapped_column(primary_key=True)
    titulo: Mapped[str] = mapped_column(String(200))
    turma: Mapped[str | None] = mapped_column(String(100))
    instrucoes: Mapped[str | None] = mapped_column(Text)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    # Linhas de escrita de cada resposta discursiva na folha de respostas.
    # Fica gravado porque a leitura das folhas digitalizadas precisa do mesmo
    # layout com que elas foram impressas.
    linhas_por_resposta: Mapped[int] = mapped_column(Integer, default=8, server_default="8")
    # Pontos de cada objetiva certa. As discursivas valem a nota máxima da questão.
    valor_objetiva: Mapped[float] = mapped_column(Float, default=1.0, server_default="1")
    # Quando o professor liberou os resultados para os alunos; vazio enquanto não liberou.
    resultados_liberados_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    itens: Mapped[list["AtividadeQuestao"]] = relationship(
        back_populates="atividade", cascade="all, delete-orphan", order_by="AtividadeQuestao.ordem"
    )
    folhas: Mapped[list["Folha"]] = relationship(
        back_populates="atividade", cascade="all, delete-orphan", order_by="Folha.numero"
    )


class AtividadeQuestao(Base):
    """Uma questão dentro de uma atividade, na posição definida pelo professor.
    A mesma questão pode estar em várias atividades."""

    __tablename__ = "atividade_questao"
    __table_args__ = (UniqueConstraint("atividade_id", "questao_id", name="uq_atividade_questao"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    atividade_id: Mapped[int] = mapped_column(ForeignKey("atividade.id"))
    questao_id: Mapped[int] = mapped_column(ForeignKey("questao.id"))
    ordem: Mapped[int] = mapped_column(Integer)

    atividade: Mapped[Atividade] = relationship(back_populates="itens")
    questao: Mapped[Questao] = relationship()


class Folha(Base):
    """Uma folha de respostas impressa: uma por aluno, identificada por um
    código único e anônimo. O código também é a chave com que o aluno consulta
    o próprio resultado, por isso é aleatório e difícil de adivinhar."""

    __tablename__ = "folha"
    __table_args__ = (
        UniqueConstraint("codigo", name="uq_folha_codigo"),
        UniqueConstraint("atividade_id", "numero", name="uq_folha_numero"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    atividade_id: Mapped[int] = mapped_column(ForeignKey("atividade.id"))
    numero: Mapped[int] = mapped_column(Integer)  # 1, 2, 3... dentro da atividade
    codigo: Mapped[str] = mapped_column(String(20))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)

    atividade: Mapped[Atividade] = relationship(back_populates="folhas")
    respostas: Mapped[list[Submissao]] = relationship(back_populates="folha")
    digitalizacoes: Mapped[list["PaginaDigitalizada"]] = relationship(
        back_populates="folha", order_by="PaginaDigitalizada.pagina"
    )


class PaginaDigitalizada(Base):
    """Uma página de folha de respostas digitalizada e enviada pelo professor.

    A folha e a página são identificadas pelo QR code. Quando o QR code não é
    lido, a página fica sem folha até o professor indicar qual é. A imagem
    fica em disco, na pasta de arquivos do sistema, e não no banco.
    """

    __tablename__ = "pagina_digitalizada"

    id: Mapped[int] = mapped_column(primary_key=True)
    atividade_id: Mapped[int] = mapped_column(ForeignKey("atividade.id", name="fk_pagina_digitalizada_atividade"))
    folha_id: Mapped[int | None] = mapped_column(ForeignKey("folha.id", name="fk_pagina_digitalizada_folha"))
    pagina: Mapped[int | None] = mapped_column(Integer)          # página da folha (1, 2...)
    arquivo: Mapped[str] = mapped_column(String(300))            # caminho relativo à pasta de arquivos
    nome_original: Mapped[str] = mapped_column(String(300))      # nome do arquivo enviado
    pagina_do_arquivo: Mapped[int] = mapped_column(Integer)      # posição no PDF enviado (1 para imagens)
    # "identificada", "sem_qr", "outra_atividade" ou "substituida" (uma mais nova ocupou o lugar)
    situacao: Mapped[str] = mapped_column(String(30))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id", name="fk_pagina_digitalizada_usuario"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)

    folha: Mapped["Folha | None"] = relationship(back_populates="digitalizacoes")

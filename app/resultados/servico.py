"""Respostas das folhas, nota de cada folha e liberação dos resultados.

A nota de uma folha só fica completa quando todas as questões têm pontos
definidos: as objetivas pela comparação com o gabarito, e as discursivas pela
decisão do professor sobre a nota sugerida (RF11). Uma discursiva em branco
vale zero sem passar pelo modelo.
"""

from dataclasses import dataclass, field

from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.correcao.discursiva import ResultadoCorrecao, compor_resposta, gerar_correcao
from app.models import (
    Atividade, Correcao, Folha, Questao, RespostaItem, RevisaoProfessor, Submissao, agora,
)

MARCACAO_MULTIPLA = "*"
ORIGEM_FOLHA = "folha"

# Situação de cada questão numa folha
SEM_RESPOSTA = "sem_resposta"          # nada registrado ainda
CERTA, ERRADA = "certa", "errada"
EM_BRANCO = "em_branco"
ANULADA = "anulada"                    # mais de uma alternativa marcada
SEM_GABARITO = "sem_gabarito"          # objetiva sem alternativa correta cadastrada
A_CORRIGIR = "a_corrigir"              # discursiva respondida, sem correção do modelo
A_REVISAR = "a_revisar"                # corrigida, esperando a decisão do professor
REVISADA = "revisada"

ROTULOS = {
    SEM_RESPOSTA: "Sem resposta registrada", CERTA: "Certa", ERRADA: "Errada", EM_BRANCO: "Em branco",
    ANULADA: "Anulada (mais de uma marcada)", SEM_GABARITO: "Sem gabarito cadastrado",
    A_CORRIGIR: "A corrigir", A_REVISAR: "Esperando revisão", REVISADA: "Nota confirmada",
}


class RespostasInvalidas(ValueError):
    """Registro recusado, com a mensagem exibida ao professor."""


# ---------------------------------------------------------------------------
# Leitura do que já existe
# ---------------------------------------------------------------------------

def respostas_da_folha(folha: Folha) -> dict[int, Submissao]:
    return {s.questao_id: s for s in folha.respostas}


def correcao_vigente(sessao: Session, submissao: Submissao) -> Correcao | None:
    """A correção mais recente da resposta. Correções anteriores continuam no banco."""
    return sessao.scalars(
        select(Correcao).where(Correcao.submissao_id == submissao.id).order_by(Correcao.id.desc())
    ).first()


def revisao_de(sessao: Session, correcao: Correcao | None) -> RevisaoProfessor | None:
    if correcao is None:
        return None
    return sessao.scalars(select(RevisaoProfessor).where(RevisaoProfessor.correcao_id == correcao.id)).first()


def gabarito(questao: Questao) -> str | None:
    corretas = [a.letra for a in questao.alternativas if a.correta]
    return corretas[0] if len(corretas) == 1 else None


def discursiva_em_branco(questao: Questao, submissao: Submissao) -> bool:
    if questao.itens:
        return not any(r.texto.strip() for r in submissao.respostas_itens)
    return not (submissao.resposta_aluno or "").strip()


# ---------------------------------------------------------------------------
# Nota da folha
# ---------------------------------------------------------------------------

@dataclass
class LinhaResultado:
    numero: int
    questao: Questao
    submissao: Submissao | None
    situacao: str
    valor: float                  # pontos possíveis
    pontos: float | None          # None enquanto não há nota definida
    correcao: Correcao | None = None
    revisao: RevisaoProfessor | None = None
    gabarito: str | None = None

    @property
    def rotulo(self) -> str:
        return ROTULOS[self.situacao]


@dataclass
class ResultadoFolha:
    folha: Folha
    linhas: list[LinhaResultado] = field(default_factory=list)

    @property
    def maximo(self) -> float:
        return sum(l.valor for l in self.linhas)

    @property
    def pontos(self) -> float:
        return sum(l.pontos or 0 for l in self.linhas)

    @property
    def respondida(self) -> bool:
        return any(l.submissao is not None for l in self.linhas)

    @property
    def completa(self) -> bool:
        """Todas as questões têm pontos definidos. Só então o aluno vê a nota."""
        return self.respondida and all(l.pontos is not None for l in self.linhas)

    def contar(self, *situacoes: str) -> int:
        return sum(1 for l in self.linhas if l.situacao in situacoes)

    @property
    def situacao(self) -> str:
        if not self.respondida:
            return "Sem respostas"
        if self.completa:
            return "Concluída"
        if self.contar(SEM_RESPOSTA):
            return "Respostas incompletas"
        if self.contar(A_CORRIGIR):
            return "A corrigir"
        if self.contar(A_REVISAR):
            return "Esperando revisão"
        return "Pendente"  # objetiva sem gabarito


def resultado_da_folha(sessao: Session, folha: Folha) -> ResultadoFolha:
    atividade = folha.atividade
    respostas = respostas_da_folha(folha)
    resultado = ResultadoFolha(folha=folha)
    for numero, item in enumerate(atividade.itens, start=1):
        questao = item.questao
        sub = respostas.get(questao.id)
        if questao.tipo == "objetiva":
            certa = gabarito(questao)
            linha = LinhaResultado(numero, questao, sub, SEM_RESPOSTA, atividade.valor_objetiva, None, gabarito=certa)
            if sub is not None:
                marcada = sub.alternativa_escolhida
                if certa is None:
                    linha.situacao = SEM_GABARITO
                elif not marcada:
                    linha.situacao, linha.pontos = EM_BRANCO, 0.0
                elif marcada == MARCACAO_MULTIPLA:
                    linha.situacao, linha.pontos = ANULADA, 0.0
                elif marcada == certa:
                    linha.situacao, linha.pontos = CERTA, atividade.valor_objetiva
                else:
                    linha.situacao, linha.pontos = ERRADA, 0.0
        else:
            linha = LinhaResultado(numero, questao, sub, SEM_RESPOSTA, questao.nota_maxima, None)
            if sub is not None:
                if discursiva_em_branco(questao, sub):
                    linha.situacao, linha.pontos = EM_BRANCO, 0.0
                else:
                    linha.correcao = correcao_vigente(sessao, sub)
                    linha.revisao = revisao_de(sessao, linha.correcao)
                    if linha.correcao is None:
                        linha.situacao = A_CORRIGIR
                    elif linha.revisao is None:
                        linha.situacao = A_REVISAR
                    else:
                        linha.situacao, linha.pontos = REVISADA, linha.revisao.nota_final
        resultado.linhas.append(linha)
    return resultado


def corrigir_discursiva(sessao: Session, submissao: Submissao, cliente: OpenAI | None,
                        usuario_id: int | None) -> ResultadoCorrecao:
    """Corrige uma resposta de folha com o pipeline das discursivas.

    Usa a resposta esperada quando a questão tem uma cadastrada: na sala de
    aula, o objetivo é a melhor correção possível, e a comparação entre as
    duas condições fica restrita ao corpus da pesquisa.
    """
    questao = sessao.get(Questao, submissao.questao_id)
    return gerar_correcao(sessao, submissao, questao.resposta_esperada is not None,
                          cliente=cliente, usuario_id=usuario_id)


def discursivas_a_corrigir(sessao: Session, atividade: Atividade, folha: Folha | None = None) -> list[Submissao]:
    """Respostas discursivas não em branco, sem nenhuma correção, na ordem das folhas."""
    folhas = [folha] if folha is not None else atividade.folhas
    pendentes = []
    for f in folhas:
        for linha in resultado_da_folha(sessao, f).linhas:
            if linha.situacao == A_CORRIGIR:
                pendentes.append(linha.submissao)
    return pendentes


# ---------------------------------------------------------------------------
# Registro das respostas
# ---------------------------------------------------------------------------

def registrar_respostas(sessao: Session, folha: Folha, dados: dict[str, str]) -> list[str]:
    """Grava as respostas digitadas da folha e devolve avisos para o professor.

    Campos esperados: `q{questao_id}` com a letra, "branco" ou "multipla" para
    as objetivas; `q{questao_id}` com o texto, ou `q{questao_id}_{letra}` por
    item, para as discursivas.

    Objetivas podem ser alteradas a qualquer momento, porque a nota é só uma
    comparação com o gabarito. Uma discursiva já corrigida não é alterada: a
    correção e a decisão do professor se referem ao texto que foi corrigido.
    """
    avisos = []
    existentes = respostas_da_folha(folha)
    for numero, item in enumerate(folha.atividade.itens, start=1):
        questao = item.questao
        chave = f"q{questao.id}"
        sub = existentes.get(questao.id)

        if questao.tipo == "objetiva":
            if chave not in dados:
                continue
            valor = dados[chave]
            letras = {a.letra for a in questao.alternativas} or set("ABCDE")
            if valor == "branco":
                marcada = None
            elif valor == "multipla":
                marcada = MARCACAO_MULTIPLA
            elif valor in letras:
                marcada = valor
            else:
                raise RespostasInvalidas(f"Questão {numero}: alternativa inválida.")
            if sub is None:
                sub = Submissao(questao_id=questao.id, folha=folha, origem=ORIGEM_FOLHA)
                sessao.add(sub)
            sub.alternativa_escolhida = marcada
            continue

        if questao.itens:
            campos = {i.letra: f"{chave}_{i.letra}" for i in questao.itens}
            if not any(c in dados for c in campos.values()):
                continue
            textos = {letra: dados.get(c, "").strip() for letra, c in campos.items()}
        else:
            if chave not in dados:
                continue
            textos = {None: dados[chave].strip()}

        if sub is not None and correcao_vigente(sessao, sub) is not None:
            atual = ({i.letra: sub.resposta_do_item(i.letra) for i in questao.itens} if questao.itens
                     else {None: sub.resposta_aluno or ""})
            if atual != textos:
                avisos.append(f"Questão {numero}: a resposta já foi corrigida e não foi alterada.")
            continue

        if sub is None:
            sub = Submissao(questao_id=questao.id, folha=folha, origem=ORIGEM_FOLHA)
            sessao.add(sub)
        if questao.itens:
            por_item = {r.item.letra: r for r in sub.respostas_itens}
            for item_q in questao.itens:
                if item_q.letra in por_item:
                    por_item[item_q.letra].texto = textos[item_q.letra]
                else:
                    sub.respostas_itens.append(RespostaItem(item=item_q, texto=textos[item_q.letra]))
            sub.resposta_aluno = compor_resposta([(i.letra, textos[i.letra]) for i in questao.itens])
        else:
            sub.resposta_aluno = textos[None]
    sessao.commit()
    return avisos


def folha_tem_respostas(atividade: Atividade) -> bool:
    return any(f.respostas for f in atividade.folhas)


# ---------------------------------------------------------------------------
# Liberação
# ---------------------------------------------------------------------------

def liberar(sessao: Session, atividade: Atividade) -> None:
    atividade.resultados_liberados_em = agora()
    sessao.commit()


def recolher(sessao: Session, atividade: Atividade) -> None:
    atividade.resultados_liberados_em = None
    sessao.commit()


def visivel_para_o_aluno(resultado: ResultadoFolha) -> bool:
    """O aluno só vê a folha depois da liberação e com todas as notas definidas."""
    return resultado.folha.atividade.resultados_liberados_em is not None and resultado.completa

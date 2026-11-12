"""Avaliação humana da leitura da escrita, feita pelo administrador.

A taxa de erro (CER) precisa de uma referência digitada letra por letra, o
que custa tempo. A avaliação é a medida rápida e complementar: para cada
resposta lida, o administrador olha a imagem e escolhe uma de três notas,
com critérios fixos para que a medida seja reproduzível:

- Correta: o texto lido é o que está na imagem; nada a ajustar.
- Pequenos erros: até três palavras a ajustar, e o sentido da resposta não muda.
- Muitos erros: mais de três palavras a ajustar, ou o sentido da resposta mudou.

Ele marca também se a revisão da IA corrigiu um erro do próprio aluno, que é
o risco principal da revisão. Os textos avaliados são copiados para a
avaliação, porque uma nova leitura da página substitui a anterior.
"""

import json
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.leitura.servico import LIDA, leituras_da_folha
from app.models import Atividade, AvaliacaoLeitura, Folha, agora

NOTAS = {
    "correta": ("Correta", "O texto lido é o que está na imagem."),
    "pequenos_erros": ("Pequenos erros", "Até três palavras a ajustar; o sentido não muda."),
    "muitos_erros": ("Muitos erros", "Mais de três palavras a ajustar, ou o sentido mudou."),
}


class AvaliacaoInvalida(ValueError):
    pass


def campos_lidos(folha: Folha) -> dict[str, dict]:
    """Para cada campo da escrita com leitura, o texto lido e de onde ele veio."""
    campos = {}
    for leitura in leituras_da_folha(folha):
        if leitura.situacao != LIDA:
            continue
        resultado = json.loads(leitura.resultado_json)
        revisoes = resultado.get("revisoes", {})
        for campo, texto in resultado.get("textos", {}).items():
            revisao = revisoes.get(campo)
            aplicada = revisao is not None and not revisao.get("descartada")
            campos[campo] = {
                "leitura": leitura, "texto": texto,
                "texto_ocr": resultado.get("textos_ocr", {}).get(campo, texto),
                "com_revisao": aplicada, "trocas": len(revisao.get("alteracoes", [])) if aplicada else 0,
            }
    return campos


def avaliacoes_da_folha(sessao: Session, folha: Folha) -> dict[str, AvaliacaoLeitura]:
    """As avaliações das leituras atuais da folha, por campo."""
    ids = [l.id for l in leituras_da_folha(folha)]
    if not ids:
        return {}
    return {a.campo: a for a in sessao.scalars(
        select(AvaliacaoLeitura).where(AvaliacaoLeitura.leitura_pagina_id.in_(ids)))}


def avaliar(sessao: Session, folha: Folha, campo: str, nota: str, corrigiu_erro_aluno: bool,
            usuario_id: int | None) -> AvaliacaoLeitura:
    if nota not in NOTAS:
        raise AvaliacaoInvalida("Nota inválida.")
    lido = campos_lidos(folha).get(campo)
    if lido is None:
        raise AvaliacaoInvalida("Este campo não tem leitura automática para avaliar.")
    leitura = lido["leitura"]
    avaliacao = sessao.scalars(select(AvaliacaoLeitura).where(
        AvaliacaoLeitura.leitura_pagina_id == leitura.id, AvaliacaoLeitura.campo == campo)).first()
    if avaliacao is None:
        avaliacao = AvaliacaoLeitura(leitura_pagina_id=leitura.id, folha_id=folha.id, campo=campo)
        sessao.add(avaliacao)
    avaliacao.nota = nota
    avaliacao.corrigiu_erro_aluno = corrigiu_erro_aluno
    avaliacao.texto_lido, avaliacao.texto_ocr = lido["texto"], lido["texto_ocr"]
    avaliacao.servico_ocr, avaliacao.com_revisao, avaliacao.trocas = leitura.servico_ocr, lido["com_revisao"], lido["trocas"]
    avaliacao.usuario_id, avaliacao.atualizado_em = usuario_id, agora()
    sessao.commit()
    return avaliacao


@dataclass
class Grupo:
    nome: str
    notas: Counter = field(default_factory=Counter)
    corrigiu_erro_aluno: int = 0
    trocas: int = 0

    @property
    def total(self) -> int:
        return sum(self.notas.values())

    def fracao(self, nota: str) -> float:
        return self.notas[nota] / self.total if self.total else 0.0


def _nome_do_grupo(a: AvaliacaoLeitura) -> str:
    servico = {"google-cloud-vision": "Cloud Vision", "google-document-ai": "Document AI"}.get(a.servico_ocr or "", "OCR")
    return f"{servico} com revisão da IA" if a.com_revisao else f"{servico} sem revisão"


def resumo(sessao: Session, atividade: Atividade | None = None) -> tuple[Grupo, list[Grupo]]:
    """O total e os grupos por condição de leitura (serviço, com ou sem revisão)."""
    consulta = select(AvaliacaoLeitura)
    if atividade is not None:
        consulta = consulta.join(Folha).where(Folha.atividade_id == atividade.id)
    # Uma folha lida de novo na mesma condição e avaliada outra vez conta uma vez só, pela avaliação mais recente.
    ultimas = {}
    for a in sessao.scalars(consulta.order_by(AvaliacaoLeitura.atualizado_em, AvaliacaoLeitura.id)):
        ultimas[(a.folha_id, a.campo, _nome_do_grupo(a))] = a
    total, grupos = Grupo("Todas"), {}
    for a in ultimas.values():
        for g in (total, grupos.setdefault(_nome_do_grupo(a), Grupo(_nome_do_grupo(a)))):
            g.notas[a.nota] += 1
            g.corrigiu_erro_aluno += a.corrigiu_erro_aluno
            g.trocas += a.trocas
    return total, sorted(grupos.values(), key=lambda g: g.nome)


def linhas_csv(sessao: Session) -> list[dict]:
    """Uma linha por avaliação, com o código da folha e sem nenhum outro dado do aluno."""
    linhas = []
    for a in sessao.scalars(select(AvaliacaoLeitura).order_by(AvaliacaoLeitura.id)):
        folha = sessao.get(Folha, a.folha_id)
        linhas.append({"atividade": folha.atividade_id, "folha": folha.codigo, "campo": a.campo, "nota": a.nota,
                       "corrigiu_erro_aluno": int(a.corrigiu_erro_aluno), "servico": a.servico_ocr or "",
                       "com_revisao": int(a.com_revisao), "trocas": a.trocas, "texto_ocr": a.texto_ocr or "",
                       "texto_lido": a.texto_lido, "atual": int(a.leitura_pagina_id is not None),
                       "avaliada_em": a.atualizado_em.isoformat(timespec="minutes")})
    return linhas

"""Avaliação humana da leitura da escrita, feita pelo administrador.

Serve para entender a assertividade da leitura com a revisão da IA, olhando a
imagem, em dois níveis:

- Cada troca feita pela revisão é marcada como certa (o texto ficou como na
  imagem), errada (a troca deixou o texto diferente da imagem) ou erro do
  aluno (a imagem mostra um erro do próprio aluno, que a IA não devia ter
  corrigido). Daí sai a taxa de acerto das trocas, que é a assertividade da
  revisão.
- O texto lido inteiro recebe uma nota: correta (o que está na imagem), com
  pequenos erros (até três palavras a ajustar, o sentido não muda) ou com
  muitos erros (mais de três palavras, ou o sentido mudou). Daí sai a
  assertividade da leitura como um todo, OCR mais revisão.

Os textos avaliados são copiados para a avaliação, porque uma nova leitura da
página substitui a anterior.
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


VEREDITOS = {
    "certa": ("Certa", "A troca deixou o texto como está na imagem."),
    "errada": ("Errada", "A troca deixou o texto diferente da imagem."),
    "erro_aluno": ("Era erro do aluno", "A imagem mostra um erro do aluno, que a IA não devia ter corrigido."),
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
                "alteracoes": revisao.get("alteracoes", []) if aplicada else [],
            }
    return campos


def avaliacoes_da_folha(sessao: Session, folha: Folha) -> dict[str, AvaliacaoLeitura]:
    """As avaliações das leituras atuais da folha, por campo."""
    ids = [l.id for l in leituras_da_folha(folha)]
    if not ids:
        return {}
    return {a.campo: a for a in sessao.scalars(
        select(AvaliacaoLeitura).where(AvaliacaoLeitura.leitura_pagina_id.in_(ids)))}


def trocas_da_avaliacao(avaliacao: AvaliacaoLeitura | None) -> list[dict]:
    return json.loads(avaliacao.trocas_json or "[]") if avaliacao is not None else []


def avaliar(sessao: Session, folha: Folha, campo: str, usuario_id: int | None, nota: str | None = None,
            troca: int | None = None, veredito: str | None = None) -> AvaliacaoLeitura:
    """Grava a nota do texto, o veredito de uma troca, ou os dois. O que não vier fica como estava."""
    if nota is not None and nota not in NOTAS:
        raise AvaliacaoInvalida("Nota inválida.")
    if troca is not None and veredito not in VEREDITOS:
        raise AvaliacaoInvalida("Veredito inválido.")
    if nota is None and troca is None:
        raise AvaliacaoInvalida("Nada para gravar.")
    lido = campos_lidos(folha).get(campo)
    if lido is None:
        raise AvaliacaoInvalida("Este campo não tem leitura automática para avaliar.")
    if troca is not None and not 0 <= troca < len(lido["alteracoes"]):
        raise AvaliacaoInvalida("Troca inexistente.")
    leitura = lido["leitura"]
    avaliacao = sessao.scalars(select(AvaliacaoLeitura).where(
        AvaliacaoLeitura.leitura_pagina_id == leitura.id, AvaliacaoLeitura.campo == campo)).first()
    if avaliacao is None:
        avaliacao = AvaliacaoLeitura(leitura_pagina_id=leitura.id, folha_id=folha.id, campo=campo)
        sessao.add(avaliacao)
    trocas = trocas_da_avaliacao(avaliacao)
    if len(trocas) != len(lido["alteracoes"]):
        trocas = [{"lido": a["lido"], "corrigido": a["corrigido"], "veredito": None} for a in lido["alteracoes"]]
    if nota is not None:
        avaliacao.nota = nota
    if troca is not None:
        trocas[troca]["veredito"] = veredito
    avaliacao.trocas_json = json.dumps(trocas, ensure_ascii=False)
    avaliacao.corrigiu_erro_aluno = any(t["veredito"] == "erro_aluno" for t in trocas)
    avaliacao.texto_lido, avaliacao.texto_ocr = lido["texto"], lido["texto_ocr"]
    avaliacao.servico_ocr, avaliacao.com_revisao, avaliacao.trocas = leitura.servico_ocr, lido["com_revisao"], lido["trocas"]
    avaliacao.usuario_id, avaliacao.atualizado_em = usuario_id, agora()
    sessao.commit()
    return avaliacao


@dataclass
class Grupo:
    nome: str
    notas: Counter = field(default_factory=Counter)
    vereditos: Counter = field(default_factory=Counter)
    corrigiu_erro_aluno: int = 0   # respostas com pelo menos uma troca que era erro do aluno
    trocas: int = 0                # trocas feitas pela revisão, avaliadas ou não

    @property
    def total(self) -> int:
        """Respostas com nota."""
        return sum(self.notas.values())

    @property
    def trocas_avaliadas(self) -> int:
        return sum(self.vereditos.values())

    def fracao(self, nota: str) -> float:
        return self.notas[nota] / self.total if self.total else 0.0

    def fracao_trocas(self, veredito: str) -> float:
        return self.vereditos[veredito] / self.trocas_avaliadas if self.trocas_avaliadas else 0.0


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
            if a.nota:
                g.notas[a.nota] += 1
            g.vereditos.update(t["veredito"] for t in trocas_da_avaliacao(a) if t.get("veredito"))
            g.corrigiu_erro_aluno += a.corrigiu_erro_aluno
            g.trocas += a.trocas
    return total, sorted(grupos.values(), key=lambda g: g.nome)


def linhas_csv(sessao: Session) -> list[dict]:
    """Uma linha por avaliação, com o código da folha e sem nenhum outro dado do aluno."""
    linhas = []
    for a in sessao.scalars(select(AvaliacaoLeitura).order_by(AvaliacaoLeitura.id)):
        folha = sessao.get(Folha, a.folha_id)
        vereditos = Counter(t.get("veredito") for t in trocas_da_avaliacao(a))
        linhas.append({"atividade": folha.atividade_id, "folha": folha.codigo, "campo": a.campo, "nota": a.nota or "",
                       "corrigiu_erro_aluno": int(a.corrigiu_erro_aluno), "servico": a.servico_ocr or "",
                       "com_revisao": int(a.com_revisao), "trocas": a.trocas,
                       "trocas_certas": vereditos["certa"], "trocas_erradas": vereditos["errada"],
                       "trocas_erro_aluno": vereditos["erro_aluno"],
                       "trocas_detalhe": a.trocas_json, "texto_ocr": a.texto_ocr or "",
                       "texto_lido": a.texto_lido, "atual": int(a.leitura_pagina_id is not None),
                       "avaliada_em": a.atualizado_em.isoformat(timespec="minutes")})
    return linhas

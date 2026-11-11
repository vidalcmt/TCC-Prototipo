"""Revisão da transcrição pela IA: corrige erros de leitura e mantém os do aluno."""

import base64
import json

import cv2
import numpy as np
import pytest

from app.config import config
from app.correcao.contratos import RevisaoTranscricaoV1, TrechoAlterado
from app.leitura import lote as lote_leitura
from app.leitura import ocr, revisor
from app.main import app
from app.models import LeituraPagina, MetricaRequisicao, Questao
from app.questoes.cliente import obter_cliente_llm
from scripts.medir_leitura import medir
from tests.falsos import ClienteFalso, resposta_falsa
from tests.test_leitura import _enviar_folha
from tests.test_resultados import _LinhaSincrona, _url, prova  # noqa: F401


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "pasta_arquivos", tmp_path)
    monkeypatch.setattr(lote_leitura.threading, "Thread", _LinhaSincrona)
    lote_leitura._andamentos.clear()


def _saida(texto, alteracoes=(), incertos=()):
    return RevisaoTranscricaoV1(texto=texto, alteracoes=[TrechoAlterado(lido=l, corrigido=c, motivo=m)
                                                          for l, c, m in alteracoes],
                                trechos_incertos=list(incertos))


RECORTE = np.full((300, 2000), 255, np.uint8)


def test_corrige_erro_de_leitura_e_mantem_erro_do_aluno(fabrica_sessao):
    lido = "O assasino entrou pela perede da casa"
    cliente = ClienteFalso(resposta_falsa(_saida("O assasino entrou pela parede da casa",
                                                 [("perede", "parede", "a letra é um a")])))
    with fabrica_sessao() as s:
        r = revisor.revisar(s, RECORTE, lido, cliente)
        metrica = s.query(MetricaRequisicao).one()
        assert metrica.tipo_questao == "transcricao" and metrica.prompt_versao == "transcricao_v1"
    assert r.texto == "O assasino entrou pela parede da casa" and r.descartada is None
    assert r.alteracoes == [{"lido": "perede", "corrigido": "parede", "motivo": "a letra é um a"}]

    # o que vai ao modelo: o texto lido e a imagem da caixa, reduzida, e nada da questão
    entrada = cliente.chamadas[0]["input"]
    conteudo = entrada[-1]["content"]
    assert conteudo[0]["type"] == "input_text" and lido in conteudo[0]["text"]
    assert conteudo[1]["type"] == "input_image" and conteudo[1]["image_url"].startswith("data:image/jpeg;base64,")
    imagem = cv2.imdecode(np.frombuffer(base64.b64decode(conteudo[1]["image_url"].split(",", 1)[1]), np.uint8),
                          cv2.IMREAD_GRAYSCALE)
    assert max(imagem.shape) == revisor.LADO_MAXIMO_PX
    assert "assasino" in entrada[0]["content"]  # o exemplo de erro do aluno está no prompt


def test_revisao_que_muda_demais_e_descartada(fabrica_sessao):
    lido = "A fotossíntese ocorre nas folhas"
    cliente = ClienteFalso(resposta_falsa(_saida("A respiração celular acontece na mitocôndria")))
    with fabrica_sessao() as s:
        r = revisor.revisar(s, RECORTE, lido, cliente)
        metrica = s.query(MetricaRequisicao).one()
        assert not metrica.sucesso and "revisão descartada" in metrica.motivo_falha
    assert r.texto == lido and "mais do que o permitido" in r.descartada


@pytest.mark.parametrize("saida,erro,motivo", [
    (None, RuntimeError("rede"), "falha na chamada"),
    (_saida("   "), None, "caixa em branco"),
])
def test_falhas_mantem_o_texto_do_ocr(fabrica_sessao, saida, erro, motivo):
    cliente = ClienteFalso(resposta_falsa(saida) if saida else None, erro=erro)
    with fabrica_sessao() as s:
        r = revisor.revisar(s, RECORTE, "texto lido", cliente)
    assert r.texto == "texto lido" and motivo in r.descartada


def test_caixa_vazia_nao_chama_o_modelo(fabrica_sessao):
    cliente = ClienteFalso(resposta_falsa(_saida("x")))
    with fabrica_sessao() as s:
        assert revisor.revisar(s, RECORTE, "  ", cliente).texto == "  "
    assert cliente.chamadas == []


def test_leitura_com_revisao_mostra_as_trocas_e_mede(fabrica_sessao, cliente_web, prova, monkeypatch):
    p = prova
    monkeypatch.setattr(config, "leitura_revisao_ia", True)
    cliente = ClienteFalso(resposta_falsa(_saida("Houve êxodo rural.", [("exodo", "êxodo", "o acento está na imagem")],
                                                 incertos=["rural"])))
    app.dependency_overrides[obter_cliente_llm] = lambda: cliente
    _enviar_folha(fabrica_sessao, cliente_web, p, {p["o1"]: "B"}, monkeypatch=monkeypatch)
    # o OCR falso lê "Houve êxodo rural."; troca uma palavra para a revisão ter o que corrigir
    original = ocr.transcrever

    def transcrever(*args, **kw):
        textos, latencia, servico = original(*args, **kw)
        return {c: t.replace("êxodo", "exodo") for c, t in textos.items()}, latencia, servico
    monkeypatch.setattr(ocr, "transcrever", transcrever)

    cliente_web.post(f"/atividades/{p['atividade']}/digitalizacoes/ler")
    pagina = cliente_web.get(_url(p)).text
    assert ">Houve êxodo rural.</textarea>" in pagina
    assert "A revisão da IA trocou" in pagina and "<s>exodo</s> por <b>êxodo</b>" in pagina
    assert "Trechos incertos:</strong> rural" in pagina
    with fabrica_sessao() as s:
        resultado = json.loads(s.query(LeituraPagina).one().resultado_json)
        enunciado = s.get(Questao, p["d"]).enunciado
    assert resultado["textos_ocr"][f"q{p['d']}"] == "Houve exodo rural."
    texto_enviado = json.dumps(cliente.chamadas[0]["input"], ensure_ascii=False)
    assert enunciado not in texto_enviado  # o modelo não vê a pergunta

    # o professor confere e mantém o texto revisado: a medida compara com e sem a revisão
    cliente_web.post(f"{_url(p)}/respostas", data={f"q{p['o1']}": "B", f"q{p['o2']}": "branco",
                                                     f"q{p['d']}": "Houve êxodo rural."})
    with fabrica_sessao() as s:
        medida = medir(s)
    assert (medida.revisados, medida.melhorou, medida.piorou) == (1, 1, 0)
    assert medida.soma_cer_revisado == 0 and medida.soma_cer_ocr > 0
    assert "Revisão da IA: 1 campo(s) revisado(s)" in medida.resumo()


def test_revisao_desligada_nao_chama_o_modelo(fabrica_sessao, cliente_web, prova, monkeypatch):
    p = prova
    monkeypatch.setattr(config, "leitura_revisao_ia", False)
    cliente = ClienteFalso(resposta_falsa(_saida("x")))
    app.dependency_overrides[obter_cliente_llm] = lambda: cliente
    _enviar_folha(fabrica_sessao, cliente_web, p, {}, monkeypatch=monkeypatch)
    cliente_web.post(f"{_url(p)}/ler")
    assert cliente.chamadas == [] and "A revisão da IA" not in cliente_web.get(_url(p)).text

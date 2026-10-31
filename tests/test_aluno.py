"""Página pública do aluno: consulta pelo código, só depois da liberação."""

import pytest

from app.aluno import router as rota_aluno
from app.contas.sessao import ControleDeTentativas
from app.correcao.contratos import CorrecaoObjetivaV3, ExplicacaoAlternativaV3
from app.models import Correcao, Folha, Questao
from tests.test_discursiva import RESPOSTA
from tests.test_resultados import _cliente_falso, _url, prova  # noqa: F401


@pytest.fixture(autouse=True)
def limpar_consultas(monkeypatch):
    monkeypatch.setattr(rota_aluno, "consultas", ControleDeTentativas(maximo=3))


def _explicacao(questao_id):
    return CorrecaoObjetivaV3(
        questao_id=str(questao_id), alternativa_correta="B", pista_do_enunciado="A palavra 'ciclo' indica repetição.",
        explicacoes=[ExplicacaoAlternativaV3(
            letra=l, correta=l == "B", tipo_de_erro=None if l == "B" else "anacronismo",
            explicacao=f"Explicação da {l}.", pista=None, conceito_envolvido="Conceito",
        ) for l in "ABCDE"],
        explicacao_correta="Caminho até a B.", nivel_dificuldade_estimado="medio",
    )


def _preparar(fabrica_sessao, cliente_web, p, liberar=True):
    """Folha 1: objetiva 1 errada (C), objetiva 2 certa, discursiva corrigida e revisada com 8."""
    with fabrica_sessao() as s:
        s.add(Correcao(questao_id=p["o1"], feedback_json=_explicacao(p["o1"]).model_dump_json(),
                       modelo="m", prompt_versao="objetiva_v3"))
        s.commit()
    cliente_web.post(f"{_url(p)}/respostas", data={f"q{p['o1']}": "C", f"q{p['o2']}": "B", f"q{p['d']}": RESPOSTA})
    _cliente_falso(p)
    cliente_web.post(f"{_url(p)}/corrigir")
    with fabrica_sessao() as s:
        cid = s.query(Correcao).filter(Correcao.submissao_id.is_not(None)).one().id
    cliente_web.post(f"/correcoes/{cid}/revisao", data={"acao": "ajustar", "nota_final": "8"})
    if liberar:
        cliente_web.post(f"/atividades/{p['atividade']}/resultados/liberar")


def test_resultado_liberado_mostra_so_o_que_e_do_aluno(fabrica_sessao, cliente_web, cliente_anonimo, prova):
    p = prova
    _preparar(fabrica_sessao, cliente_web, p)
    cliente_web.post("/sair")
    r = cliente_anonimo.get(f"/r/{p['codigos'][0]}")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    html = r.text
    assert "Prova" in html and "de 12 pontos" in html and ">9<" in html.replace("</svg>", ">")  # 1 + 8
    assert "Você marcou <strong>C</strong>" in html and "A resposta correta é <strong>B</strong>" in html
    assert "Explicação da C." in html and "Caminho até a B." in html and "A palavra &#39;ciclo&#39;" in html
    assert "Você identificou bem a consequência" in html  # feedback para o aluno
    # nada do que é do professor
    assert "Justificativa 1." not in html and "Critério 1" not in html and "sugerida" not in html
    assert "Sair" not in html and "/atividades" not in html


def test_codigo_digitado_de_qualquer_jeito(fabrica_sessao, cliente_anonimo, prova):
    digitado = prova["codigos"][0].replace("-", " ").lower()
    r = cliente_anonimo.get("/resultado", params={"codigo": digitado}, follow_redirects=False)
    assert r.headers["location"] == f"/r/{prova['codigos'][0]}"


def test_antes_da_liberacao_e_folha_incompleta(fabrica_sessao, cliente_web, cliente_anonimo, prova):
    p = prova
    _preparar(fabrica_sessao, cliente_web, p, liberar=False)
    html = cliente_anonimo.get(f"/r/{p['codigos'][0]}").text
    assert "ainda não liberou" in html and "Explicação" not in html and "de 12 pontos" not in html
    cliente_web.post(f"/atividades/{p['atividade']}/resultados/liberar")
    cliente_web.post(f"{_url(p, 1)}/respostas", data={f"q{p['o1']}": "B"})  # folha 2 incompleta
    assert "ainda está em correção" in cliente_anonimo.get(f"/r/{p['codigos'][1]}").text


def test_codigo_inexistente_e_limite_de_tentativas(cliente_anonimo, prova):
    for _ in range(3):
        r = cliente_anonimo.get("/r/AAAA-AAAA")
        assert r.status_code == 404 and "Código não encontrado" in r.text
    r = cliente_anonimo.get(f"/r/{prova['codigos'][0]}")
    assert r.status_code == 429 and "Muitas tentativas" in r.text


def test_formulario_do_codigo(cliente_anonimo):
    html = cliente_anonimo.get("/resultado").text
    assert 'name="codigo"' in html and "noindex" in html


def test_canhoto_tem_qr_com_link(fabrica_sessao, cliente_web, prova):
    html = cliente_web.get(f"/atividades/{prova['atividade']}/folhas/imprimir").text
    assert html.count('class="qr qr-canhoto"') == 3 and "aponte a câmera" in html

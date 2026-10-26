"""Lista de questões: paginação de 50 em 50 e filtros."""

import re

import pytest

from app.models import Correcao, Questao, RevisaoProfessor


def _criar(fabrica_sessao):
    """120 questões: as pares discursivas de 2025, as ímpares objetivas do ENEM 2023."""
    with fabrica_sessao() as s:
        for i in range(1, 121):
            discursiva = i % 2 == 0
            s.add(Questao(
                tipo="discursiva" if discursiva else "objetiva",
                enunciado=f"Enunciado {i} sobre {'feudalismo' if i % 10 == 0 else 'outro tema'}.",
                area="ciencias-humanas" if i <= 60 else "matematica",
                fonte="Fuvest 2025" if discursiva else "ENEM 2023",
                ano=2025 if discursiva else 2023,
            ))
        s.commit()
        # Questão 2 com correção pendente; questão 4 com correção já revisada; questão 1 com explicação.
        pendente = Correcao(questao_id=2, feedback_json="{}", modelo="m", prompt_versao="p", nota_sugerida=5)
        revisada = Correcao(questao_id=4, feedback_json="{}", modelo="m", prompt_versao="p", nota_sugerida=5)
        explicacao = Correcao(questao_id=1, feedback_json="{}", modelo="m", prompt_versao="p")
        s.add_all([pendente, revisada, explicacao])
        s.flush()
        s.add(RevisaoProfessor(correcao_id=revisada.id, nota_sugerida=5, nota_final=5, aceitou_sugestao=True))
        s.commit()


def _numeros(html: str) -> list[int]:
    return [int(n) for n in re.findall(r'<td><a href="/questoes/(\d+)">\d+</a></td>', html)]


def test_paginas_de_50(fabrica_sessao, cliente_web):
    _criar(fabrica_sessao)
    primeira = cliente_web.get("/questoes").text
    assert _numeros(primeira) == list(range(1, 51))
    assert "Mostrando 1 a 50 de 120 questões." in primeira
    assert 'href="/questoes?pagina=2"' in primeira and "Anterior" not in primeira

    terceira = cliente_web.get("/questoes?pagina=3").text
    assert _numeros(terceira) == list(range(101, 121)) and "Próxima" not in terceira
    assert _numeros(cliente_web.get("/questoes?pagina=99").text) == list(range(101, 121))


@pytest.mark.parametrize("consulta, esperado", [
    ("tipo=discursiva", 60),
    ("tipo=objetiva&area=matematica", 30),
    ("busca=FEUDALISMO", 12),
    ("fonte=Fuvest+2025&ano=2025", 60),
    ("ano=2023", 60),
    ("numero=7", 1),
    ("situacao=pendente", 1),
    ("situacao=sem_correcao", 117),
])
def test_filtros(fabrica_sessao, cliente_web, consulta, esperado):
    _criar(fabrica_sessao)
    pagina = cliente_web.get(f"/questoes?{consulta}").text
    texto = "questão" if esperado == 1 else "questões"
    assert f"de {esperado} {texto} encontradas." in pagina
    if consulta == "situacao=pendente":
        assert _numeros(pagina) == [2]


def test_filtros_continuam_ao_trocar_de_pagina(fabrica_sessao, cliente_web):
    _criar(fabrica_sessao)
    pagina = cliente_web.get("/questoes?tipo=objetiva&busca=Enunciado").text
    assert "de 60 questões encontradas" in pagina
    assert 'href="/questoes?busca=Enunciado&amp;tipo=objetiva&amp;pagina=2"' in pagina
    segunda = cliente_web.get("/questoes?busca=Enunciado&tipo=objetiva&pagina=2").text
    assert _numeros(segunda) == [101, 103, 105, 107, 109, 111, 113, 115, 117, 119]
    assert 'value="objetiva" selected' in segunda and "Limpar" in segunda


def test_filtro_sem_resultado(fabrica_sessao, cliente_web):
    _criar(fabrica_sessao)
    pagina = cliente_web.get("/questoes?busca=inexistente").text
    assert "Nenhuma questão com esses filtros." in pagina


def test_opcoes_dos_filtros_vem_do_banco(fabrica_sessao, cliente_web):
    _criar(fabrica_sessao)
    pagina = cliente_web.get("/questoes").text
    for opcao in ['<option value="matematica"', '<option value="Fuvest 2025"', '<option value="2023"']:
        assert opcao in pagina

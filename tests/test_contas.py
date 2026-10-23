"""Contas, login, permissões, limite diário e páginas novas."""

import re
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import config
from app.contas.senhas import conferir, gerar_resumo, senha_provisoria
from app.contas.sessao import ControleDeTentativas, MAX_TENTATIVAS
from app.main import app
from app.models import Correcao, MetricaRequisicao, Questao, RevisaoProfessor, Submissao, Usuario
from app.templates_config import quando, saudacao
from tests.conftest import SENHA_TESTE, criar_usuario, entrar


# ---------- senhas ----------

def test_resumo_da_senha_confere_so_com_a_senha_certa():
    resumo = gerar_resumo("minha senha")
    assert resumo.startswith("scrypt$") and "minha senha" not in resumo
    assert conferir("minha senha", resumo)
    assert not conferir("outra senha", resumo)
    assert not conferir("minha senha", "lixo")
    assert gerar_resumo("minha senha") != resumo  # sal aleatório


def test_parametros_de_producao_seguem_a_owasp(monkeypatch):
    import app.contas.senhas as senhas
    monkeypatch.setattr(senhas, "N", 2**17)
    resumo = gerar_resumo("minha senha")
    assert resumo.split("$")[1:4] == ["131072", "8", "1"] and conferir("minha senha", resumo)


def test_senha_provisoria_tem_formato_facil_de_ditar():
    assert re.fullmatch(r"[a-z2-9]{4}-[a-z2-9]{4}-[a-z2-9]{4}", senha_provisoria())


def test_bloqueio_apos_tentativas_e_liberacao_depois_da_janela():
    agora = [1000.0]
    controle = ControleDeTentativas(relogio=lambda: agora[0])
    for _ in range(MAX_TENTATIVAS):
        controle.registrar_erro("a@b.com")
    assert controle.bloqueado("a@b.com") and not controle.bloqueado("c@d.com")
    agora[0] += 11 * 60
    assert not controle.bloqueado("a@b.com")


# ---------- toda rota exige login ----------

PUBLICAS = {"/entrar", "/sair", "/saude"}


def _rotas():
    for caminho, operacoes in app.openapi()["paths"].items():
        for metodo in operacoes:
            yield metodo.upper(), caminho


def test_nenhuma_rota_fica_aberta_sem_login(cliente_anonimo):
    verificadas = 0
    for metodo, caminho in _rotas():
        if caminho in PUBLICAS:
            continue
        url = re.sub(r"\{[^}]+\}", "1", caminho)
        resposta = cliente_anonimo.request(metodo, url, follow_redirects=False)
        assert resposta.status_code == 303, f"{metodo} {caminho} respondeu {resposta.status_code}"
        assert resposta.headers["location"].startswith("/entrar"), f"{metodo} {caminho}"
        verificadas += 1
    assert verificadas >= 18


def test_get_sem_login_guarda_a_pagina_para_voltar_depois(cliente_anonimo):
    resposta = cliente_anonimo.get("/questoes?x=1", follow_redirects=False)
    assert resposta.headers["location"] == "/entrar?proximo=/questoes%3Fx%3D1"


def test_arquivos_estaticos_e_pagina_de_entrar_sao_publicos(cliente_anonimo):
    assert cliente_anonimo.get("/static/estilo.css").status_code == 200
    pagina = cliente_anonimo.get("/entrar")
    assert pagina.status_code == 200 and "Entrar" in pagina.text and "data-alternar-tema" in pagina.text


def test_documentacao_automatica_da_api_fica_desligada(cliente_anonimo):
    assert cliente_anonimo.get("/docs").status_code == 404
    assert cliente_anonimo.get("/openapi.json").status_code == 404


# ---------- entrar e sair ----------

def test_entrar_com_senha_certa_e_email_em_maiusculas(fabrica_sessao, cliente_anonimo):
    criar_usuario(fabrica_sessao, email="prof@teste.com", papel="avaliador")
    resposta = entrar(cliente_anonimo, "PROF@Teste.com ")
    assert resposta.headers["location"] == "/"
    assert cliente_anonimo.get("/").status_code == 200


@pytest.mark.parametrize("senha, ativo", [("errada", True), (SENHA_TESTE, False)])
def test_senha_errada_ou_conta_desativada_nao_entram(fabrica_sessao, cliente_anonimo, senha, ativo):
    criar_usuario(fabrica_sessao, email="prof@teste.com", ativo=ativo)
    resposta = cliente_anonimo.post("/entrar", data={"email": "prof@teste.com", "senha": senha})
    assert resposta.status_code == 401 and "incorretos" in resposta.text
    assert cliente_anonimo.get("/", follow_redirects=False).status_code == 303


def test_bloqueia_depois_de_tentativas_erradas_mesmo_com_a_senha_certa(fabrica_sessao, cliente_anonimo):
    criar_usuario(fabrica_sessao, email="prof@teste.com")
    for _ in range(MAX_TENTATIVAS):
        cliente_anonimo.post("/entrar", data={"email": "prof@teste.com", "senha": "errada"})
    resposta = cliente_anonimo.post("/entrar", data={"email": "prof@teste.com", "senha": SENHA_TESTE})
    assert resposta.status_code == 429 and "Muitas tentativas" in resposta.text


@pytest.mark.parametrize("proximo, destino", [
    ("/questoes/3", "/questoes/3"),
    ("https://site-falso.com", "/"),
    ("//site-falso.com", "/"),
    ("", "/"),
])
def test_volta_para_a_pagina_pedida_so_se_for_interna(fabrica_sessao, cliente_anonimo, proximo, destino):
    criar_usuario(fabrica_sessao, email="prof@teste.com")
    resposta = cliente_anonimo.post("/entrar", data={"email": "prof@teste.com", "senha": SENHA_TESTE,
                                                     "proximo": proximo}, follow_redirects=False)
    assert resposta.headers["location"] == destino


def test_sair_encerra_a_sessao(cliente_web):
    cliente_web.post("/sair")
    assert cliente_web.get("/", follow_redirects=False).status_code == 303


# ---------- senha provisória e troca ----------

def test_senha_provisoria_obriga_a_trocar_antes_de_usar(fabrica_sessao, cliente_anonimo):
    criar_usuario(fabrica_sessao, email="novo@teste.com", precisa_trocar=True)
    assert entrar(cliente_anonimo, "novo@teste.com").headers["location"] == "/trocar-senha"
    assert cliente_anonimo.get("/questoes", follow_redirects=False).headers["location"] == "/trocar-senha"

    for dados, erro in [
        ({"senha_atual": "errada", "nova": "abcdefgh1", "confirmacao": "abcdefgh1"}, "não confere"),
        ({"senha_atual": SENHA_TESTE, "nova": "curta", "confirmacao": "curta"}, "pelo menos 8"),
        ({"senha_atual": SENHA_TESTE, "nova": "abcdefgh1", "confirmacao": "abcdefgh2"}, "não é igual"),
        ({"senha_atual": SENHA_TESTE, "nova": SENHA_TESTE, "confirmacao": SENHA_TESTE}, "diferente da atual"),
    ]:
        resposta = cliente_anonimo.post("/trocar-senha", data=dados)
        assert resposta.status_code == 400 and erro in resposta.text

    resposta = cliente_anonimo.post("/trocar-senha", data={
        "senha_atual": SENHA_TESTE, "nova": "nova-senha-boa", "confirmacao": "nova-senha-boa"})
    assert "Senha trocada" in resposta.text
    assert cliente_anonimo.get("/questoes").status_code == 200


def test_trocar_senha_encerra_sessoes_em_outros_navegadores(fabrica_sessao, cliente_web):
    outro = TestClient(app)
    entrar(outro, "admin@teste.com")
    assert outro.get("/", follow_redirects=False).status_code == 200

    cliente_web.post("/trocar-senha", data={"senha_atual": SENHA_TESTE, "nova": "outra-senha-1",
                                            "confirmacao": "outra-senha-1"})
    assert cliente_web.get("/", follow_redirects=False).status_code == 200   # este continua
    assert outro.get("/", follow_redirects=False).status_code == 303         # o outro sai


# ---------- papéis ----------

def test_avaliador_nao_ve_metricas_nem_usuarios(fabrica_sessao, cliente_anonimo):
    criar_usuario(fabrica_sessao, email="prof@teste.com", nome="Bruno Prof", papel="avaliador")
    entrar(cliente_anonimo, "prof@teste.com")
    for url in ["/metricas", "/metricas/revisoes.csv", "/usuarios"]:
        resposta = cliente_anonimo.get(url)
        assert resposta.status_code == 403 and "só para administradores" in resposta.text
    inicio = cliente_anonimo.get("/")
    assert 'href="/metricas"' not in inicio.text and 'href="/usuarios"' not in inicio.text
    assert "Custo de" not in inicio.text
    assert cliente_anonimo.get("/questoes").status_code == 200


# ---------- gestão de usuários ----------

def _senha_mostrada(html: str) -> str:
    return re.search(r'class="senha-mostrada">([^<]+)<', html).group(1)


def test_criar_conta_mostra_senha_provisoria_que_funciona(fabrica_sessao, cliente_web):
    pagina = cliente_web.post("/usuarios", data={"nome": "Carla Prof", "email": "Carla@Teste.com",
                                                 "papel": "avaliador"})
    assert "Conta criada para Carla Prof" in pagina.text
    senha = _senha_mostrada(pagina.text)

    with fabrica_sessao() as s:
        nova = s.query(Usuario).filter_by(email="carla@teste.com").one()
        assert nova.precisa_trocar_senha and nova.papel == "avaliador" and senha not in nova.senha_resumo

    outro = TestClient(app)
    assert entrar(outro, "carla@teste.com", senha).headers["location"] == "/trocar-senha"
    assert "senha-mostrada" not in cliente_web.get("/usuarios").text  # aparece só uma vez


@pytest.mark.parametrize("dados, erro", [
    ({"nome": "", "email": "x@teste.com"}, "Informe o nome"),
    ({"nome": "X", "email": "sem-arroba"}, "e-mail válido"),
    ({"nome": "X", "email": "admin@teste.com"}, "Já existe uma conta"),
])
def test_criar_conta_invalida_mostra_erro(cliente_web, dados, erro):
    resposta = cliente_web.post("/usuarios", data={"papel": "avaliador", **dados})
    assert resposta.status_code == 400 and erro in resposta.text


def test_nova_senha_invalida_a_anterior(fabrica_sessao, cliente_web):
    uid = criar_usuario(fabrica_sessao, email="prof@teste.com", papel="avaliador")
    pagina = cliente_web.post(f"/usuarios/{uid}/redefinir-senha")
    senha = _senha_mostrada(pagina.text)
    assert TestClient(app).post("/entrar", data={"email": "prof@teste.com", "senha": SENHA_TESTE}).status_code == 401
    assert entrar(TestClient(app), "prof@teste.com", senha).headers["location"] == "/trocar-senha"


def test_desativar_derruba_a_sessao_aberta(fabrica_sessao, cliente_web):
    uid = criar_usuario(fabrica_sessao, email="prof@teste.com", papel="avaliador")
    outro = TestClient(app)
    entrar(outro, "prof@teste.com")
    cliente_web.post(f"/usuarios/{uid}/situacao", data={"ativo": "0"})
    assert outro.get("/", follow_redirects=False).status_code == 303
    cliente_web.post(f"/usuarios/{uid}/situacao", data={"ativo": "1"})
    entrar(outro, "prof@teste.com")


def test_admin_nao_desativa_a_si_mesmo(fabrica_sessao, cliente_web):
    with fabrica_sessao() as s:
        meu_id = s.query(Usuario).filter_by(email="admin@teste.com").one().id
    resposta = cliente_web.post(f"/usuarios/{meu_id}/situacao", data={"ativo": "0"})
    assert resposta.status_code == 400 and "sua própria conta" in resposta.text


def test_ultimo_admin_ativo_nao_pode_ser_desativado(fabrica_sessao):
    from app.contas.servico import ContaInvalida, alterar_situacao
    with fabrica_sessao() as s:
        a = Usuario(nome="A", email="a@t.com", papel="admin", senha_resumo=gerar_resumo("x" * 8))
        b = Usuario(nome="B", email="b@t.com", papel="avaliador", senha_resumo=gerar_resumo("x" * 8))
        s.add_all([a, b])
        s.commit()
        with pytest.raises(ContaInvalida, match="pelo menos um administrador"):
            alterar_situacao(s, a, False, quem_altera=b)


# ---------- quem fez o quê, e limite diário ----------

def _correcao_discursiva(fabrica_sessao):
    from app.correcao.contratos import AnaliseCriterio, CorrecaoDiscursiva
    with fabrica_sessao() as s:
        q = Questao(tipo="discursiva", enunciado="Explique.", nota_maxima=10)
        s.add(q)
        s.flush()
        sub = Submissao(questao_id=q.id, resposta_aluno="Resposta.", codigo_corpus="R007")
        s.add(sub)
        s.flush()
        c = Correcao(submissao_id=sub.id, questao_id=q.id, nota_sugerida=6.5, usou_resposta_esperada=False,
                     modelo="m", prompt_versao="discursiva_v1",
                     feedback_json=CorrecaoDiscursiva(
                         questao_id=str(q.id), usou_resposta_esperada=False, nota_sugerida=6.5, nota_maxima=10,
                         confianca="media", feedback_elaborado="F.",
                         analise_criterios=[AnaliseCriterio(criterio="C", peso=10, status="parcial",
                                                            justificativa="J.", trecho_citado=None)],
                     ).model_dump_json())
        s.add(c)
        s.commit()
        return c.id, sub.id


def test_revisao_guarda_quem_decidiu_e_a_pagina_mostra(fabrica_sessao, cliente_web):
    cid, sid = _correcao_discursiva(fabrica_sessao)
    pagina = cliente_web.post(f"/correcoes/{cid}/revisao", data={"acao": "aceitar"})
    assert "por Ana Admin" in pagina.text
    with fabrica_sessao() as s:
        r = s.query(RevisaoProfessor).one()
        assert s.get(Usuario, r.usuario_id).email == "admin@teste.com"


def test_fila_de_revisao_no_inicio_e_na_barra(fabrica_sessao, cliente_web):
    cid, sid = _correcao_discursiva(fabrica_sessao)
    inicio = cliente_web.get("/")
    assert "Resposta R007" in inicio.text and 'class="contador"' in inicio.text
    assert "1 correção espera a sua decisão" in inicio.text
    assert "Resposta R007" in cliente_web.get("/revisar").text

    cliente_web.post(f"/correcoes/{cid}/revisao", data={"acao": "ajustar", "nota_final": "8"})
    inicio = cliente_web.get("/")
    assert "Nenhuma correção espera decisão" in inicio.text and 'class="contador"' not in inicio.text
    assert "ajustada para 8 por você" in inicio.text


def test_limite_diario_impede_novas_chamadas(fabrica_sessao, cliente_web, monkeypatch):
    from app.questoes.cliente import obter_cliente_llm
    from tests.falsos import ClienteFalso
    monkeypatch.setattr(config, "limite_chamadas_dia", 1)
    with fabrica_sessao() as s:
        admin_id = s.query(Usuario).filter_by(email="admin@teste.com").one().id
        s.add(MetricaRequisicao(usuario_id=admin_id, modelo_solicitado="m", prompt_versao="p",
                                latencia_ms=1, sucesso=True))
        q = Questao(tipo="objetiva", enunciado="E")
        s.add(q)
        s.commit()
        qid = q.id
    cliente_falso = ClienteFalso()
    app.dependency_overrides[obter_cliente_llm] = lambda: cliente_falso

    resposta = cliente_web.post(f"/questoes/{qid}/explicar")
    assert resposta.status_code == 429 and "Limite de hoje atingido" in resposta.text
    assert cliente_falso.chamadas == []  # o modelo não foi chamado
    with fabrica_sessao() as s:
        assert s.query(MetricaRequisicao).count() == 1


def test_chamada_ao_modelo_guarda_quem_pediu(fabrica_sessao, cliente_web):
    from app.questoes.cliente import obter_cliente_llm
    from tests.falsos import ClienteFalso
    _, sid = _correcao_discursiva(fabrica_sessao)
    app.dependency_overrides[obter_cliente_llm] = lambda: ClienteFalso(erro=ConnectionError("x"))
    cliente_web.post(f"/respostas/{sid}/corrigir", data={"condicao": "sem"})
    with fabrica_sessao() as s:
        m = s.query(MetricaRequisicao).one()
        assert s.get(Usuario, m.usuario_id).email == "admin@teste.com"


# ---------- textos de data e hora ----------

AGORA = datetime(2026, 10, 23, 15, 0, tzinfo=timezone.utc)  # 12h00 em Brasília


@pytest.mark.parametrize("data, texto", [
    (datetime(2026, 10, 23, 14, 59, 30), "agora há pouco"),
    (datetime(2026, 10, 23, 14, 40), "há 20 minutos"),
    (datetime(2026, 10, 23, 13, 0), "há 2 horas"),
    (datetime(2026, 10, 22, 15, 0), "ontem"),
    (datetime(2026, 10, 20, 15, 0), "há 3 dias"),
    (datetime(2026, 10, 1, 15, 0), "em 01/10/2026"),
])
def test_tempo_relativo(data, texto):
    assert quando(data, agora=AGORA) == texto


def test_saudacao_pelo_horario_de_brasilia():
    assert saudacao(datetime(2026, 10, 23, 11, 0, tzinfo=timezone.utc)) == "Bom dia"      # 8h
    assert saudacao(datetime(2026, 10, 23, 18, 0, tzinfo=timezone.utc)) == "Boa tarde"    # 15h
    assert saudacao(datetime(2026, 10, 24, 1, 0, tzinfo=timezone.utc)) == "Boa noite"     # 22h


def test_nome_com_aspas_nao_quebra_a_confirmacao(fabrica_sessao, cliente_web):
    criar_usuario(fabrica_sessao, email="d@teste.com", nome="Ana D'Ávila <b>", papel="avaliador")
    pagina = cliente_web.get("/usuarios").text
    assert "Ana D&#39;Ávila &lt;b&gt;" in pagina and "<b>" not in pagina

import warnings

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

warnings.filterwarnings("ignore", message="SECRET_KEY não definida")

import app.contas.senhas  # noqa: E402
import app.models  # noqa: E402,F401

# Nos testes, um custo menor de scrypt deixa a suíte rápida. O valor de
# produção é conferido em test_contas.py.
app.contas.senhas.N = 2**14
from app.database import Base  # noqa: E402

SENHA_TESTE = "senha-de-teste-123"


@pytest.fixture
def fabrica_sessao():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def sessao(fabrica_sessao):
    with fabrica_sessao() as s:
        yield s


def criar_usuario(fabrica_sessao, email="admin@teste.com", nome="Ana Admin", papel="admin",
                  senha=SENHA_TESTE, precisa_trocar=False, ativo=True):
    from app.contas.senhas import gerar_resumo
    from app.models import Usuario
    with fabrica_sessao() as s:
        u = Usuario(nome=nome, email=email, papel=papel, senha_resumo=gerar_resumo(senha),
                    precisa_trocar_senha=precisa_trocar, ativo=ativo)
        s.add(u)
        s.commit()
        return u.id


@pytest.fixture
def cliente_anonimo(fabrica_sessao):
    """Cliente web com o banco de teste, sem login."""
    from fastapi.testclient import TestClient

    from app.contas.sessao import tentativas
    from app.database import obter_fabrica_sessao, obter_sessao
    from app.main import app

    def sessao_de_teste():
        with fabrica_sessao() as s:
            yield s

    app.dependency_overrides[obter_sessao] = sessao_de_teste
    app.dependency_overrides[obter_fabrica_sessao] = lambda: fabrica_sessao
    tentativas._erros.clear()
    from app.resultados import lote
    lote._andamentos.clear()
    yield TestClient(app)
    app.dependency_overrides.clear()


def entrar(cliente, email, senha=SENHA_TESTE):
    resposta = cliente.post("/entrar", data={"email": email, "senha": senha}, follow_redirects=False)
    assert resposta.status_code == 303, resposta.text
    return resposta


@pytest.fixture
def cliente_web(fabrica_sessao, cliente_anonimo):
    """Cliente web já logado como administrador."""
    criar_usuario(fabrica_sessao)
    entrar(cliente_anonimo, "admin@teste.com")
    return cliente_anonimo

"""Páginas de conta: entrar, sair, trocar senha e gestão de usuários."""

from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.contas.senhas import conferir, problema_na_senha_nova
from app.contas.servico import (
    PAPEIS, ContaInvalida, alterar_situacao, autenticar, criar_conta, normalizar_email,
    redefinir_senha, trocar_senha,
)
from app.contas.sessao import encerrar_sessao, exigir_admin, exigir_login, iniciar_sessao, tentativas
from app.database import obter_sessao
from app.models import RevisaoProfessor, Usuario
from app.templates_config import templates

publico = APIRouter(tags=["contas"])
protegido = APIRouter(tags=["contas"], dependencies=[Depends(exigir_login)])
administracao = APIRouter(tags=["contas"], dependencies=[Depends(exigir_admin)])


def destino_seguro(proximo: str | None) -> str:
    """Só aceita caminhos internos, para que o link de login não leve a outro site."""
    if not proximo:
        return "/"
    partes = urlparse(proximo)
    if partes.scheme or partes.netloc or not proximo.startswith("/") or proximo.startswith("//"):
        return "/"
    return proximo


# ---------------------------------------------------------------------------
# Entrar e sair
# ---------------------------------------------------------------------------

@publico.get("/entrar", response_class=HTMLResponse)
def pagina_entrar(request: Request, proximo: str | None = None):
    return templates.TemplateResponse(request, "entrar.html", {"proximo": proximo or "", "email": "", "erro": None})


@publico.post("/entrar", response_class=HTMLResponse)
def entrar(request: Request, email: str = Form(""), senha: str = Form(""), proximo: str = Form(""),
           sessao: Session = Depends(obter_sessao)):
    chave = normalizar_email(email)

    def recusar(mensagem: str, status: int):
        return templates.TemplateResponse(request, "entrar.html", {
            "proximo": proximo, "email": email, "erro": mensagem,
        }, status_code=status)

    if tentativas.bloqueado(chave):
        return recusar("Muitas tentativas erradas para este e-mail. Espere 10 minutos e tente de novo.", 429)

    usuario = autenticar(sessao, email, senha)
    if usuario is None:
        tentativas.registrar_erro(chave)
        return recusar("E-mail ou senha incorretos, ou conta desativada.", 401)

    tentativas.limpar(chave)
    iniciar_sessao(request, usuario)
    if usuario.precisa_trocar_senha:
        return RedirectResponse("/trocar-senha", status_code=303)
    return RedirectResponse(destino_seguro(proximo), status_code=303)


@publico.post("/sair")
def sair(request: Request):
    encerrar_sessao(request)
    return RedirectResponse("/entrar", status_code=303)


# ---------------------------------------------------------------------------
# Trocar senha
# ---------------------------------------------------------------------------

@protegido.get("/trocar-senha", response_class=HTMLResponse)
def pagina_trocar_senha(request: Request):
    return templates.TemplateResponse(request, "trocar_senha.html", {"erro": None})


@protegido.post("/trocar-senha", response_class=HTMLResponse)
def salvar_senha(request: Request, senha_atual: str = Form(""), nova: str = Form(""), confirmacao: str = Form(""),
                 sessao: Session = Depends(obter_sessao)):
    usuario = sessao.get(Usuario, request.state.usuario.id)
    erro = None
    if not conferir(senha_atual, usuario.senha_resumo):
        erro = "A senha atual não confere."
    elif nova == senha_atual:
        erro = "A nova senha precisa ser diferente da atual."
    else:
        erro = problema_na_senha_nova(nova, confirmacao)
    if erro:
        return templates.TemplateResponse(request, "trocar_senha.html", {"erro": erro}, status_code=400)

    trocar_senha(sessao, usuario, nova)
    iniciar_sessao(request, usuario)  # renova a sessão com a marca da senha nova
    return RedirectResponse("/?senha=trocada", status_code=303)


# ---------------------------------------------------------------------------
# Gestão de usuários (só administradores)
# ---------------------------------------------------------------------------

def _pagina_usuarios(request: Request, sessao: Session, **extra):
    revisoes = (
        select(RevisaoProfessor.usuario_id, func.count().label("n"))
        .group_by(RevisaoProfessor.usuario_id).subquery()
    )
    linhas = sessao.execute(
        select(Usuario, func.coalesce(revisoes.c.n, 0))
        .outerjoin(revisoes, revisoes.c.usuario_id == Usuario.id)
        .order_by(Usuario.ativo.desc(), Usuario.nome)
    ).all()
    contexto = {"linhas": linhas, "papeis": PAPEIS, "dados": {}, "erro": None, "criada": None, "redefinida": None}
    contexto.update(extra)
    return templates.TemplateResponse(request, "usuarios.html", contexto,
                                      status_code=400 if contexto["erro"] else 200)


@administracao.get("/usuarios", response_class=HTMLResponse)
def listar_usuarios(request: Request, sessao: Session = Depends(obter_sessao)):
    return _pagina_usuarios(request, sessao)


@administracao.post("/usuarios", response_class=HTMLResponse)
def criar_usuario(request: Request, nome: str = Form(""), email: str = Form(""), papel: str = Form("avaliador"),
                  sessao: Session = Depends(obter_sessao)):
    try:
        conta = criar_conta(sessao, nome, email, papel)
    except ContaInvalida as erro:
        return _pagina_usuarios(request, sessao, erro=str(erro), dados={"nome": nome, "email": email, "papel": papel})
    return _pagina_usuarios(request, sessao, criada=conta)


def _usuario(sessao: Session, usuario_id: int) -> Usuario:
    usuario = sessao.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return usuario


@administracao.post("/usuarios/{usuario_id}/redefinir-senha", response_class=HTMLResponse)
def redefinir(request: Request, usuario_id: int, sessao: Session = Depends(obter_sessao)):
    usuario = _usuario(sessao, usuario_id)
    senha = redefinir_senha(sessao, usuario)
    return _pagina_usuarios(request, sessao, redefinida={"usuario": usuario, "senha": senha})


@administracao.post("/usuarios/{usuario_id}/situacao", response_class=HTMLResponse)
def mudar_situacao(request: Request, usuario_id: int, ativo: str = Form(...),
                   sessao: Session = Depends(obter_sessao)):
    usuario = _usuario(sessao, usuario_id)
    try:
        alterar_situacao(sessao, usuario, ativo == "1", quem_altera=request.state.usuario)
    except ContaInvalida as erro:
        return _pagina_usuarios(request, sessao, erro=str(erro))
    return RedirectResponse("/usuarios", status_code=303)

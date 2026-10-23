"""Regras das contas: criar, autenticar, trocar e redefinir senha."""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from functools import cache

from app.contas.senhas import conferir, gerar_resumo, senha_provisoria


@cache
def _resumo_de_referencia() -> str:
    return gerar_resumo("conta-inexistente")
from app.models import Usuario, agora

PAPEIS = {"avaliador": "Avaliador", "admin": "Administrador"}


class ContaInvalida(ValueError):
    pass


@dataclass
class ContaCriada:
    usuario: Usuario
    senha_provisoria: str


def normalizar_email(email: str) -> str:
    return (email or "").strip().lower()


def buscar_por_email(sessao: Session, email: str) -> Usuario | None:
    return sessao.scalars(select(Usuario).where(Usuario.email == normalizar_email(email))).first()


def criar_conta(sessao: Session, nome: str, email: str, papel: str = "avaliador") -> ContaCriada:
    nome, email = (nome or "").strip(), normalizar_email(email)
    if not nome:
        raise ContaInvalida("Informe o nome.")
    if "@" not in email or "." not in email.split("@")[-1]:
        raise ContaInvalida("Informe um e-mail válido.")
    if papel not in PAPEIS:
        raise ContaInvalida("Papel inválido.")
    if buscar_por_email(sessao, email):
        raise ContaInvalida("Já existe uma conta com este e-mail.")

    senha = senha_provisoria()
    usuario = Usuario(nome=nome, email=email, papel=papel, senha_resumo=gerar_resumo(senha),
                      ativo=True, precisa_trocar_senha=True)
    sessao.add(usuario)
    sessao.commit()
    return ContaCriada(usuario=usuario, senha_provisoria=senha)


def autenticar(sessao: Session, email: str, senha: str) -> Usuario | None:
    """Devolve o usuário se e-mail e senha conferem e a conta está ativa."""
    usuario = buscar_por_email(sessao, email)
    if usuario is None:
        # Confere contra um resumo qualquer, com o mesmo custo de uma conta
        # real, para que o tempo de resposta não revele se o e-mail existe.
        conferir(senha, _resumo_de_referencia())
        return None
    if not usuario.ativo or not conferir(senha, usuario.senha_resumo):
        return None
    usuario.ultimo_acesso = agora()
    sessao.commit()
    return usuario


def trocar_senha(sessao: Session, usuario: Usuario, nova: str) -> None:
    usuario.senha_resumo = gerar_resumo(nova)
    usuario.precisa_trocar_senha = False
    sessao.commit()


def redefinir_senha(sessao: Session, usuario: Usuario) -> str:
    """Gera nova senha provisória; a pessoa troca no próximo acesso."""
    senha = senha_provisoria()
    usuario.senha_resumo = gerar_resumo(senha)
    usuario.precisa_trocar_senha = True
    sessao.commit()
    return senha


def alterar_situacao(sessao: Session, usuario: Usuario, ativo: bool, quem_altera: Usuario) -> None:
    if usuario.id == quem_altera.id and not ativo:
        raise ContaInvalida("Você não pode desativar a sua própria conta.")
    if not ativo and usuario.eh_admin:
        admins_ativos = sessao.scalar(
            select(func.count(Usuario.id)).where(Usuario.papel == "admin", Usuario.ativo.is_(True))
        )
        if admins_ativos <= 1:
            raise ContaInvalida("O sistema precisa de pelo menos um administrador ativo.")
    usuario.ativo = ativo
    sessao.commit()

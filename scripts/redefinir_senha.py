"""Gera uma senha provisória nova para uma conta, pela linha de comando.

Uso:
    python -m scripts.redefinir_senha --email voce@exemplo.com

Serve para quando o administrador esquece a própria senha. A senha anterior
deixa de valer, e a nova precisa ser trocada no primeiro acesso. Para ver os
e-mails cadastrados: python -m scripts.redefinir_senha --listar
"""

import argparse

from sqlalchemy import select

from app.contas.servico import buscar_por_email, redefinir_senha
from app.database import SessionLocal
from app.models import Usuario


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--email")
    grupo.add_argument("--listar", action="store_true", help="mostra as contas cadastradas")
    args = parser.parse_args()

    with SessionLocal() as sessao:
        if args.listar:
            for u in sessao.scalars(select(Usuario).order_by(Usuario.id)):
                situacao = "ativa" if u.ativo else "desativada"
                print(f"{u.id}  {u.email}  {u.papel}  {situacao}")
            return
        usuario = buscar_por_email(sessao, args.email)
        if usuario is None:
            raise SystemExit("Nenhuma conta com esse e-mail. Use --listar para ver as contas.")
        senha = redefinir_senha(sessao, usuario)
        print(f"Nova senha provisória para {usuario.nome} (anote agora, ela não aparece de novo): {senha}")


if __name__ == "__main__":
    main()

"""Cria a primeira conta de administrador (ou outra, quando necessário).

Uso:
    python -m scripts.criar_admin --nome "Felipe Vidal" --email felipe@exemplo.com

Mostra uma senha provisória uma única vez. No primeiro acesso, o sistema pede
para trocá-la.
"""

import argparse

from app.contas.servico import ContaInvalida, criar_conta
from app.database import SessionLocal


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--nome", required=True)
    parser.add_argument("--email", required=True)
    args = parser.parse_args()

    with SessionLocal() as sessao:
        try:
            conta = criar_conta(sessao, args.nome, args.email, papel="admin")
        except ContaInvalida as erro:
            raise SystemExit(f"Não foi possível criar a conta: {erro}")
    print(f"Administrador criado: {conta.usuario.nome} <{conta.usuario.email}>")
    print(f"Senha provisória (anote agora, ela não aparece de novo): {conta.senha_provisoria}")


if __name__ == "__main__":
    main()

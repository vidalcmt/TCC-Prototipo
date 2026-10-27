#!/usr/bin/env bash
# Substitui o banco do servidor por um arquivo tcc.db enviado do computador.
#
# Uso, dentro da máquina, depois de enviar o arquivo pela janela SSH
# (engrenagem, "Fazer upload de arquivo"), que o coloca na sua pasta pessoal:
#   sudo bash /opt/devolutiva/deploy/usar_banco.sh ~/tcc.db
#
# O banco atual do servidor é copiado antes, para poder voltar atrás. As
# contas de usuário vêm junto com o arquivo enviado.

set -euo pipefail

PASTA=/opt/devolutiva
USUARIO=devolutiva
NOVO="${1:-}"

if [[ $EUID -ne 0 ]]; then
  echo "Rode com sudo: sudo bash $0 caminho/do/tcc.db" >&2
  exit 1
fi
if [[ -z "$NOVO" || ! -f "$NOVO" ]]; then
  echo "Informe o arquivo enviado, por exemplo: sudo bash $0 ~/tcc.db" >&2
  exit 1
fi
cd "$PASTA"

echo "==> Parando a aplicação"
systemctl stop devolutiva.service

if [[ -f tcc.db ]]; then
  ANTIGO="/var/backups/devolutiva/tcc-substituido-$(date +%Y%m%d-%H%M%S).db"
  cp tcc.db "$ANTIGO"
  echo "==> Banco anterior guardado em $ANTIGO"
fi

install -o "$USUARIO" -g "$USUARIO" -m 640 "$NOVO" tcc.db
echo "==> Atualizando a estrutura do banco enviado"
sudo -u "$USUARIO" .venv/bin/alembic upgrade head

systemctl start devolutiva.service
echo "Pronto. O site já usa o banco enviado."

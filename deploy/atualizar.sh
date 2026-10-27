#!/usr/bin/env bash
# Atualiza o site com a versão mais recente da branch main.
#
# Uso, dentro da máquina: sudo bash /opt/devolutiva/deploy/atualizar.sh
#
# Faz uma cópia do banco antes de qualquer mudança, traz o código novo,
# instala dependências novas, aplica as migrações e reinicia a aplicação.

set -euo pipefail

PASTA=/opt/devolutiva
USUARIO=devolutiva

if [[ $EUID -ne 0 ]]; then
  echo "Rode com sudo: sudo bash $0" >&2
  exit 1
fi
cd "$PASTA"
como_app() { sudo -u "$USUARIO" "$@"; }

echo "==> Cópia do banco antes de atualizar"
como_app .venv/bin/python -m scripts.copia_banco --destino /var/backups/devolutiva --dias 30

echo "==> Código novo"
como_app git pull --ff-only

echo "==> Dependências e banco"
como_app .venv/bin/pip install -q -r requirements.txt
como_app .venv/bin/alembic upgrade head

# Arquivos de serviço podem ter mudado junto com o código.
install -m 644 deploy/devolutiva.service /etc/systemd/system/devolutiva.service
install -m 644 deploy/devolutiva-copia.service /etc/systemd/system/devolutiva-copia.service
install -m 644 deploy/devolutiva-copia.timer /etc/systemd/system/devolutiva-copia.timer
systemctl daemon-reload

echo "==> Reiniciando"
systemctl restart devolutiva.service
for _ in $(seq 1 20); do
  curl -fsS http://127.0.0.1:8000/saude >/dev/null 2>&1 && break
  sleep 1
done
if curl -fsS http://127.0.0.1:8000/saude >/dev/null 2>&1; then
  echo "Atualizado: $(git log -1 --format='%h %s')"
else
  echo "A aplicação não respondeu. Veja o erro com: sudo journalctl -u devolutiva -n 50" >&2
  exit 1
fi

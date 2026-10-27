#!/usr/bin/env bash
# Instala a Devolutiva numa máquina virtual Debian 12 do Google Cloud.
#
# Uso, dentro da máquina (janela SSH do navegador):
#   sudo apt-get update && sudo apt-get install -y git
#   sudo git clone https://github.com/vidalcmt/TCC-Prototipo.git /opt/devolutiva
#   sudo bash /opt/devolutiva/deploy/instalar.sh
#
# Sem argumento, o endereço do site é montado a partir do IP externo da
# máquina, no formato 34-95-10-20.sslip.io. Para usar um domínio próprio,
# passe-o como argumento: sudo bash instalar.sh devolutiva.exemplo.com.br
#
# Pode ser rodado de novo sem estragar nada: o .env existente é mantido.

set -euo pipefail

PASTA=/opt/devolutiva
USUARIO=devolutiva
COPIAS=/var/backups/devolutiva

if [[ $EUID -ne 0 ]]; then
  echo "Rode com sudo: sudo bash $0" >&2
  exit 1
fi
if [[ ! -f "$PASTA/app/main.py" ]]; then
  echo "Não encontrei o projeto em $PASTA. Clone o repositório nessa pasta antes." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
echo "==> Endereço do site"
DOMINIO="${1:-}"
if [[ -z "$DOMINIO" ]]; then
  IP=$(curl -fsS -H "Metadata-Flavor: Google" \
    "http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip")
  DOMINIO="${IP//./-}.sslip.io"
fi
echo "    $DOMINIO"

# ---------------------------------------------------------------------------
echo "==> Pacotes do sistema"
apt-get update -q
apt-get install -y -q python3 python3-venv git curl gnupg debian-keyring debian-archive-keyring apt-transport-https

if ! command -v caddy >/dev/null; then
  echo "==> Caddy (servidor que cuida do HTTPS)"
  curl -1sLf "https://dl.cloudsmith.io/public/caddy/stable/gpg.key" \
    | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf "https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt" \
    > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -q
  apt-get install -y -q caddy
fi

# ---------------------------------------------------------------------------
echo "==> Usuário de sistema que roda a aplicação"
if ! id "$USUARIO" >/dev/null 2>&1; then
  useradd --system --home-dir "$PASTA" --shell /usr/sbin/nologin "$USUARIO"
fi
chown -R "$USUARIO:$USUARIO" "$PASTA"
como_app() { sudo -u "$USUARIO" "$@"; }

echo "==> Ambiente Python e dependências"
cd "$PASTA"
[[ -d .venv ]] || como_app python3 -m venv .venv
como_app .venv/bin/pip install -q --upgrade pip
como_app .venv/bin/pip install -q -r requirements.txt

# ---------------------------------------------------------------------------
if [[ ! -f "$PASTA/.env" ]]; then
  echo "==> Arquivo .env"
  echo "    Cole a chave da API da OpenAI e tecle Enter. Ela não aparece na tela."
  read -rsp "    Chave: " CHAVE
  echo
  if [[ -z "$CHAVE" ]]; then
    echo "Nenhuma chave informada. Rode o instalador de novo." >&2
    exit 1
  fi
  SEGREDO=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
  umask 077
  cat > "$PASTA/.env" <<EOF
OPENAI_API_KEY=$CHAVE
MODELO=gpt-6.1-sol
SECRET_KEY=$SEGREDO
COOKIE_SEGURO=true
LIMITE_CHAMADAS_DIA=60
EOF
  umask 022
  unset CHAVE SEGREDO
  chown "$USUARIO:$USUARIO" "$PASTA/.env"
  chmod 600 "$PASTA/.env"
else
  echo "==> .env já existe; mantido como está"
fi

echo "==> Banco de dados"
como_app .venv/bin/alembic upgrade head

# ---------------------------------------------------------------------------
echo "==> Serviços"
install -d -o "$USUARIO" -g "$USUARIO" -m 750 "$COPIAS"
install -m 644 deploy/devolutiva.service /etc/systemd/system/devolutiva.service
install -m 644 deploy/devolutiva-copia.service /etc/systemd/system/devolutiva-copia.service
install -m 644 deploy/devolutiva-copia.timer /etc/systemd/system/devolutiva-copia.timer
sed "s/DOMINIO/$DOMINIO/" deploy/Caddyfile > /etc/caddy/Caddyfile

systemctl daemon-reload
systemctl enable --now devolutiva.service devolutiva-copia.timer
systemctl restart devolutiva.service
systemctl reload caddy || systemctl restart caddy

echo "==> Conferindo"
for _ in $(seq 1 20); do
  if curl -fsS http://127.0.0.1:8000/saude >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
if curl -fsS http://127.0.0.1:8000/saude >/dev/null 2>&1; then
  echo "    Aplicação no ar."
else
  echo "    A aplicação não respondeu. Veja o erro com: sudo journalctl -u devolutiva -n 50" >&2
  exit 1
fi

cat <<EOF

Pronto. O site fica em:

    https://$DOMINIO

O certificado HTTPS é emitido no primeiro acesso e pode levar até um minuto.

Próximo passo, criar a sua conta de administrador:

    cd $PASTA && sudo -u $USUARIO .venv/bin/python -m scripts.criar_admin --nome "Seu Nome" --email voce@exemplo.com

EOF

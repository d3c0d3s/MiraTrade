#!/usr/bin/env bash
# Deja el contenedor listo para MiraTrade. Se ejecuta DENTRO del contenedor, como root.
# Es idempotente: repetirlo no rompe nada.
set -euo pipefail

USER_NAME="${USER_NAME:-miratrade}"
HOME_DIR="/opt/miratrade"
REPO="${REPO:-https://github.com/d3c0d3s/MiraTrade.git}"
BRANCH="${BRANCH:-claude/swing-trades-analysis-fjb9lo}"

echo "== paquetes =="
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
# python3-venv y build-essential porque pandas y numpy traen ruedas, pero pdfplumber y sus
# dependencias no siempre. git para traer el repo y poder actualizarlo sin copiar ficheros a mano.
apt-get install -y -qq python3 python3-venv python3-dev build-essential git ca-certificates curl \
                       sqlite3 tzdata
# El proyecto razona en horario de Nueva York (ventanas de presentación, cierres). Tener el
# contenedor en UTC y convertir explícitamente evita el error de fijarse en la hora local de un
# servidor que nadie mira.
timedatectl set-timezone UTC 2>/dev/null || ln -sf /usr/share/zoneinfo/UTC /etc/localtime

echo "== usuario de servicio =="
id -u "$USER_NAME" >/dev/null 2>&1 || useradd --system --create-home --home-dir "$HOME_DIR" \
                                               --shell /usr/sbin/nologin "$USER_NAME"
install -d -o "$USER_NAME" -g "$USER_NAME" -m 750 "$HOME_DIR" \
        "$HOME_DIR/data" "$HOME_DIR/data/MirandasGroup" "$HOME_DIR/reports" "$HOME_DIR/app"

echo "== código =="
if [ -d "$HOME_DIR/src/.git" ]; then
  sudo -u "$USER_NAME" git -C "$HOME_DIR/src" fetch --all --quiet
  sudo -u "$USER_NAME" git -C "$HOME_DIR/src" checkout --quiet "$BRANCH"
  sudo -u "$USER_NAME" git -C "$HOME_DIR/src" pull --quiet --ff-only
else
  sudo -u "$USER_NAME" git clone --quiet --branch "$BRANCH" "$REPO" "$HOME_DIR/src"
fi

echo "== entorno de Python =="
sudo -u "$USER_NAME" python3 -m venv "$HOME_DIR/venv"
sudo -u "$USER_NAME" "$HOME_DIR/venv/bin/pip" install --quiet --upgrade pip
# `web` para la API, `congress` sólo mientras el uso sea personal: las declaraciones del Congreso
# no se pueden usar comercialmente (5 U.S.C. app. § 105(c)). Ver docs/LICENCIAS.md.
sudo -u "$USER_NAME" "$HOME_DIR/venv/bin/pip" install --quiet -e "$HOME_DIR/src[web,congress]"

echo "== dónde vive todo =="
# Las mismas variables que en Windows, para que no haya dos convenciones de rutas.
cat > /etc/miratrade.env <<EOF
MIRANDAS_DATA=$HOME_DIR/data/MirandasGroup
MIRATRADE_HOME=$HOME_DIR/app
MIRATRADE_REPORTS=$HOME_DIR/reports
MIRATRADE_CACHE=$HOME_DIR/cache
# La SEC pide un user-agent que identifique a quien pregunta. Pon aquí un correo real tuyo.
MIRATRADE_SEC_UA=MiraTrade research CAMBIAME@example.com
PYTHONUTF8=1
EOF
chmod 640 /etc/miratrade.env
chown root:"$USER_NAME" /etc/miratrade.env

echo
echo "Listo. Falta, en este orden:"
echo "  1. Editar MIRATRADE_SEC_UA en /etc/miratrade.env con un correo real."
echo "  2. Traer la base de datos (ver deploy/TRASPASO.md, paso 4). NO la copies en caliente."
echo "  3. Instalar las unidades de systemd:  deploy/systemd/instalar.sh"
echo "  4. Cloudflare Tunnel + Access:        deploy/cloudflared/LEEME.md"

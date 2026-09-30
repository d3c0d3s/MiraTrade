#!/usr/bin/env bash
# Instala las unidades. Se ejecuta DENTRO del contenedor, como root. Idempotente.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

install -m 644 "$HERE"/miratrade-*.service "$HERE"/miratrade-*.timer /etc/systemd/system/
systemctl daemon-reload

systemctl enable --now miratrade-web.service
systemctl enable --now miratrade-scan.timer
systemctl enable --now miratrade-backup.timer

echo "== estado =="
systemctl --no-pager --lines=3 status miratrade-web.service || true
systemctl list-timers --no-pager 'miratrade-*'
echo
echo "Comprobación: la API responde en local y no autentica (por eso escucha sólo en 127.0.0.1)."
curl -fsS http://127.0.0.1:8787/api/health | head -c 400; echo

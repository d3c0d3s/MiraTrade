#!/usr/bin/env bash
# Crea el contenedor de MiraTrade en Odin. Se ejecuta EN EL NODO PROXMOX, como root.
#
# No es idempotente a propósito: crear dos veces el mismo contenedor debe fallar, no sobrescribir
# uno que ya tiene datos dentro.
set -euo pipefail

CTID="${CTID:-210}"
HOSTNAME="${HOSTNAME_CT:-miratrade}"
# Disco: la base de datos son 358 MB hoy y crece con cada descarga; el venv ocupa ~900 MB. 20 GB
# deja margen para un año largo sin tener que ampliar el volumen, que es la operación molesta.
DISK_GB="${DISK_GB:-20}"
MEMORY_MB="${MEMORY_MB:-3072}"      # el backtest carga el panel entero en memoria
CORES="${CORES:-4}"
BRIDGE="${BRIDGE:-vmbr0}"
STORAGE="${STORAGE:-local-lvm}"
TEMPLATE_STORE="${TEMPLATE_STORE:-local}"
TEMPLATE="${TEMPLATE:-debian-12-standard_12.7-1_amd64.tar.zst}"
# Sin IP fija por defecto: que la dé el DHCP y se le reserve en el UniFi, que es donde vive el
# resto del direccionamiento. Poner IP aquí duplica esa decisión en dos sitios.
NET="${NET:-name=eth0,bridge=${BRIDGE},ip=dhcp}"
SSH_KEYS="${SSH_KEYS:-/root/.ssh/miratrade_authorized_keys}"

echo "== comprobaciones previas =="
pveversion >/dev/null || { echo "esto no es un nodo Proxmox"; exit 1; }
if pct status "$CTID" >/dev/null 2>&1; then
  echo "ERROR: el contenedor $CTID ya existe. Elige otro CTID o bórralo a conciencia."
  exit 1
fi
pvesm list "$TEMPLATE_STORE" | grep -q "$TEMPLATE" || {
  echo "La plantilla $TEMPLATE no está en $TEMPLATE_STORE. Descárgala con:"
  echo "  pveam update && pveam available | grep debian-12"
  echo "  pveam download $TEMPLATE_STORE $TEMPLATE"
  exit 1
}
[ -s "$SSH_KEYS" ] || {
  echo "Falta $SSH_KEYS con las llaves públicas autorizadas."
  echo "Créalo primero: una llave por línea. Sin contraseñas: el acceso es SOLO por llave."
  exit 1
}

echo "== creando $CTID ($HOSTNAME) =="
pct create "$CTID" "${TEMPLATE_STORE}:vztmpl/${TEMPLATE}" \
  --hostname "$HOSTNAME" \
  --cores "$CORES" --memory "$MEMORY_MB" --swap 1024 \
  --rootfs "${STORAGE}:${DISK_GB}" \
  --net0 "$NET" \
  --features nesting=1 \
  --unprivileged 1 \
  --onboot 1 \
  --ssh-public-keys "$SSH_KEYS" \
  --description "MiraTrade: API y web. No envía órdenes. docs/ALCANCE.md"

pct start "$CTID"
sleep 6
echo "== arrancado =="
pct exec "$CTID" -- bash -lc 'ip -4 addr show eth0 | awk "/inet /{print \$2}"'
echo
echo "Siguiente: copia deploy/lxc/preparar.sh dentro y ejecútalo."
echo "  pct push $CTID deploy/lxc/preparar.sh /root/preparar.sh"
echo "  pct exec $CTID -- bash /root/preparar.sh"

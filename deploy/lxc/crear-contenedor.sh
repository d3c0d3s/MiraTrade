#!/usr/bin/env bash
# Crea el contenedor de MiraTrade en Odin. Se ejecuta EN EL NODO PROXMOX, como root.
#
# No es idempotente a propósito: crear dos veces el mismo contenedor debe fallar, no sobrescribir
# uno que ya tiene datos dentro.
set -euo pipefail

# Convención de esta red: el CTID son los dos últimos octetos de su IP. 150210 es 192.168.150.210,
# y el contenedor del túnel, 150253, es 192.168.150.253. Los números de abajo no son arbitrarios y
# tienen que moverse juntos.
CTID="${CTID:-150210}"
HOSTNAME="${HOSTNAME_CT:-miratrade}"
# Disco: la base son 375 MB hoy y crece con cada descarga; el venv ~900 MB, y FinBERT en ONNX añade
# ~700 MB entre runtime y modelo. 50 GB deja margen de años sin ampliar el volumen, que es la
# operación molesta.
DISK_GB="${DISK_GB:-50}"
MEMORY_MB="${MEMORY_MB:-10240}"     # el backtest carga el panel entero en memoria
CORES="${CORES:-4}"
BRIDGE="${BRIDGE:-vmbr0}"
STORAGE="${STORAGE:-local-lvm}"
TEMPLATE_STORE="${TEMPLATE_STORE:-local}"
TEMPLATE="${TEMPLATE:-debian-12-standard_12.7-1_amd64.tar.zst}"
# IP fija, no DHCP: a este contenedor lo referencian el túnel desde el CT 150253 y una regla de
# cortafuegos por origen. Las dos se rompen en silencio si la dirección cambia.
IPV4="${IPV4:-192.168.150.210/24}"
GATEWAY="${GATEWAY:-192.168.150.254}"
NAMESERVER="${NAMESERVER:-192.168.150.101}"
SEARCHDOMAIN="${SEARCHDOMAIN:-miratechcloud.com}"
NET="${NET:-name=eth0,bridge=${BRIDGE},ip=${IPV4},gw=${GATEWAY}}"
SSH_KEYS="${SSH_KEYS:-/root/.ssh/miratrade_authorized_keys}"
# Quién puede abrir el 8787. Solo el contenedor del túnel: la API verifica el token de Access, y
# esto es la segunda cerradura de la misma puerta, la que no depende de que el código acierte.
TUNNEL_CT_IP="${TUNNEL_CT_IP:-192.168.150.253}"

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
  --cores "$CORES" --memory "$MEMORY_MB" --swap 2048 \
  --rootfs "${STORAGE}:${DISK_GB}" \
  --net0 "$NET" \
  --nameserver "$NAMESERVER" --searchdomain "$SEARCHDOMAIN" \
  --features nesting=1 \
  --unprivileged 1 \
  --onboot 1 \
  --ssh-public-keys "$SSH_KEYS" \
  --description "MiraTrade: API y web. No envía órdenes. docs/ALCANCE.md"

echo "== cortafuegos: solo el contenedor del túnel llega al 8787 =="
# La API verifica el token de Cloudflare Access. Esto es la otra cerradura de la misma puerta: si
# alguna vez el código fallara, un portátil cualquiera de la red seguiría sin poder abrirla.
mkdir -p /etc/pve/firewall
cat > "/etc/pve/firewall/${CTID}.fw" <<FW
[OPTIONS]
enable: 1
policy_in: DROP
policy_out: ACCEPT

[RULES]
IN ACCEPT -source ${TUNNEL_CT_IP} -p tcp -dport 8787 -log nolog
IN ACCEPT -p tcp -dport 22 -log nolog
IN ACCEPT -p icmp -log nolog
FW
echo "  escrito /etc/pve/firewall/${CTID}.fw (origen permitido: ${TUNNEL_CT_IP})"
echo "  el cortafuegos del datacenter debe estar activo para que aplique:"
echo "     pvesh get /cluster/firewall/options"

pct start "$CTID"
sleep 6
echo "== arrancado =="
pct exec "$CTID" -- bash -lc 'ip -4 addr show eth0 | awk "/inet /{print \$2}"'
echo
echo "Siguiente: copia deploy/lxc/preparar.sh dentro y ejecútalo."
echo "  pct push $CTID deploy/lxc/preparar.sh /root/preparar.sh"
echo "  pct exec $CTID -- bash /root/preparar.sh"

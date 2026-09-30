# Túnel y acceso

Se ejecuta **dentro del contenedor**, como root.

```bash
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg \
  | tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" \
  > /etc/apt/sources.list.d/cloudflared.list
apt-get update -qq && apt-get install -y cloudflared

cloudflared tunnel login                 # abre una URL: autorízala en tu cuenta
cloudflared tunnel create miratrade      # anota el UUID que imprime
cloudflared tunnel route dns miratrade miratrade.miratechcloud.com

install -d -m 700 /etc/cloudflared
# copia config.yml ajustado con el UUID y el dominio
cloudflared service install
systemctl enable --now cloudflared
```

## Lo que no se puede saltar

**Pon Cloudflare Access delante antes de publicar el DNS.** Zero Trust → Access → Applications →
Self-hosted, el hostname de arriba, política *Allow* por tu correo.

La API no tiene autenticación propia, a propósito: media autenticación sería peor que ninguna,
porque alguien se fiaría de ella. Sin Access, ese hostname es la base de datos entera en internet.

## Lo que no pasa por el túnel

Nada que toque credenciales de bróker. Eso se hace desde dentro de la red, por la VPN de UniFi.
La web no envía órdenes (`miratrade/web/__init__.py`) y no debe empezar a hacerlo por esta vía.

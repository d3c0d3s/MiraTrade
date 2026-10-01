# Túnel y acceso

cloudflared **ya está instalado** en el CT `150253` (`192.168.150.253`). No hay que instalar nada:
hay que añadir un destino al túnel que ya funciona y poner una política delante.

El registro DNS de `miratrade.srv.miratechcloud.com` ya existe, así que tampoco hace falta
`cloudflared tunnel route dns`.

## El orden importa

**La política de Access va antes que el ingress.** Al revés, hay una ventana —minutos u horas, lo
que se tarde en volver— en la que ese hostname sirve la base de datos entera a internet.

### 1. La política

Cloudflare Zero Trust → Access → Applications → Add → Self-hosted:

- Dominio: `miratrade.srv.miratechcloud.com`
- Política: *Allow*, por tu correo, o por el grupo de tu IdP si ya hay Authentik o Entra detrás
- Guardar y copiar el **Application Audience (AUD) Tag**

Esos dos valores van a `/etc/miratrade.env` del CT 150210:

```
MIRATRADE_ACCESS_TEAM=<el de <equipo>.cloudflareaccess.com>
MIRATRADE_ACCESS_AUD=<el AUD tag>
```

La API **verifica la firma** de ese token: comprueba que lo firma una clave que Cloudflare publica
para tu equipo, que la audiencia es la de esta aplicación —un token de otra de tus apps no abre
esta— y que no ha caducado. La cabecera por sí sola no prueba nada; cualquiera puede mandar una
cabecera.

### 2. El ingress, en el CT 150253

En `/etc/cloudflared/config.yml`, **antes** de la regla final `http_status:404`:

```yaml
  - hostname: miratrade.srv.miratechcloud.com
    service: http://192.168.150.210:8787
    originRequest:
      connectTimeout: 30s
```

```bash
cloudflared tunnel ingress validate
systemctl restart cloudflared
```

La regla final tiene que seguir siendo la última: sin ella cloudflared no arranca, y con ella en
otro sitio un hostname mal escrito acabaría sirviendo algo que nadie quería servir.

## Comprobarlo

```bash
# desde el CT del túnel: responde
curl -fsS http://192.168.150.210:8787/api/health

# desde fuera, sin pasar por Access: debe ser 403, no la página
curl -s -o /dev/null -w '%{http_code}\n' https://miratrade.srv.miratechcloud.com/api/health
```

Si lo segundo devuelve 200, la política no está puesta.

## Lo que no pasa por el túnel

Nada que toque credenciales de bróker. Eso se hace desde dentro de la red, por la VPN de UniFi. La
web no envía órdenes (`miratrade/web/__init__.py`) y no debe empezar a hacerlo por esta vía.

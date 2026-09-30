# Despliegue

Nada de aquí es Python, nadie lo importa y no se instala con el paquete. Está en el repo porque un
despliegue que solo vive en la cabeza de alguien no es reproducible, y porque el día que haga falta
rehacerlo será el día en que algo se ha roto.

Vacío por ahora. Lo que va a vivir aquí, y las decisiones ya tomadas:

| | Qué |
|---|---|
| `lxc/` | el contenedor en Proxmox (`odin.main.miratechcloud.com`): creación, paquetes, usuario |
| `systemd/` | la unidad de la API, y los temporizadores que hoy son `schtasks` en Windows |
| `cloudflared/` | el túnel, y Cloudflare Access delante del panel |

## Lo que ya está decidido

* **Solo por llaves.** Toda la autenticación a Odin y a Vili es por llave SSH. Ninguna contraseña en
  ningún archivo de aquí, nunca.
* **Los secretos no viven en el repo.** Hoy están en el Administrador de credenciales de Windows;
  en el servidor van a `systemd-creds` con el TPM. Un token de bróker en un archivo del repo es un
  token comprometido.
* **El túnel es para el panel, no para las credenciales.** Cloudflare Access delante de la web; lo
  que toque credenciales de bróker se hace por la VPN de UniFi, desde dentro.
* **El servidor no envía órdenes.** Ver `miratrade/web/__init__.py`.

## Lo que falta decidir

* Si la API y el frontend van en el mismo contenedor o en dos.
* Dónde vive `market.db` y quién la respalda: hoy la copia diaria la hace
  `miratrade/backup.py` en Windows, y eso tiene que moverse con los datos.
* Cómo se autentica la web. Está disponible el Windows Server 2025 de la red local; la alternativa
  más simple es Cloudflare Access sin nada detrás.

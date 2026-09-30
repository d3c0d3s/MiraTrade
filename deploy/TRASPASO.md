# Traspaso: desplegar MiraTrade en Odin

Para la sesión que tiene acceso a la red local. La sesión de MiraTrade no puede llegar a Odin: el
puerto correcto es **9922** y responde, pero ninguna de las llaves de la máquina de trabajo está
en `authorized_keys`, y tras cuatro intentos la limitación de tasa empezó a cortar las conexiones.

Todo lo que sigue está en el repositorio, en `deploy/`. No hay que inventar nada; hay que
ejecutarlo en orden y comprobar lo que se dice al final de cada paso.

- Repo: `https://github.com/d3c0d3s/MiraTrade`
- Rama: `claude/swing-trades-analysis-fjb9lo`, commit `c8ad03b` o posterior

## Qué es esto y qué no

MiraTrade descarga presentaciones del SEC, precios y cadenas de opciones, las guarda en un SQLite
y las enseña. Lo que se despliega es **la API y la web**, que sustituyen a la app de escritorio.

Tres cosas que no son negociables y que el código ya obliga:

1. **No envía órdenes.** Ni ahora ni por esta vía. Las credenciales del bróker y la decisión de
   operar se quedan en la máquina de la persona.
2. **La API no autentica.** Escucha sólo en `127.0.0.1` y delante va Cloudflare Access. Media
   autenticación sería peor que ninguna, porque alguien se fiaría de ella.
3. **Solo llaves.** Ni una contraseña en un fichero, en ninguno de los pasos.

---

## 0 · Antes de nada: rotar la contraseña de root de Proxmox

No es parte del despliegue, es más urgente que él.

La contraseña actual de root de Proxmox está **en texto plano en 43 ficheros** de la máquina de
trabajo: transcritos de Claude de cuatro proyectos, ficheros de memoria, reglas de permisos en
`settings.local.json`, y —lo peor— en ficheros `.env` y `prod.env` de despliegue de
RippedAndRenew, más un `DEPLOY_GUIDE.md`.

Comprobado: **ninguno está seguido por git**, así que no se ha publicado. Pero los `.env` son
ficheros que se despliegan, así que conviene comprobar si esa contraseña acabó también en el
hosting de RippedAndRenew.

```bash
passwd root
```

Rotarla vuelve inofensivas las 43 copias de una vez. Perseguirlas una a una no es realista.

---

## 1 · Dejar entrar a la máquina de trabajo (opcional, pero recomendado)

Si se quiere que la sesión de MiraTrade pueda operar el contenedor después, hay que añadir su
llave. Es **una sola línea** — si el copiado la parte en dos, sshd la ignora en silencio:

```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMqgdZmS3If27LasiBSGXie2vLqhE6ru+Odp7bSczOor ladmin@mirandasgroup.com
```

**Ponerla en el contenedor, no en el nodo.** MiraTrade necesita un Debian con Python, no acceso al
hipervisor donde viven todos los demás servicios. Eso se hace solo en el paso 2, con
`/root/.ssh/miratrade_authorized_keys`.

Si aun así falla luego, lo que lo dice todo es el registro del servidor mientras se intenta:

```bash
journalctl -u ssh -f
sshd -T | grep -iE "pubkeyauthentication|authorizedkeysfile|allowusers|allowgroups"
```

---

## 2 · Crear el contenedor

**En el nodo Proxmox, como root.**

```bash
git clone -b claude/swing-trades-analysis-fjb9lo https://github.com/d3c0d3s/MiraTrade /tmp/mt
cd /tmp/mt

# una llave pública por línea, las que deban poder entrar al contenedor
vi /root/.ssh/miratrade_authorized_keys

# comprobar antes que la plantilla y el almacenamiento son los de esta máquina
pveam available | grep debian-12
pvesm status

CTID=210 STORAGE=local-lvm BRIDGE=vmbr0 bash deploy/lxc/crear-contenedor.sh
```

El script **se niega a continuar** si el CTID ya existe, si falta la plantilla o si no hay llaves.
Imprime la IP al terminar: anotarla y reservarla en el UniFi.

## 3 · Preparar el contenedor

```bash
pct push 210 /tmp/mt/deploy/lxc/preparar.sh /root/preparar.sh
pct exec 210 -- bash /root/preparar.sh
pct exec 210 -- vi /etc/miratrade.env     # poner un correo real en MIRATRADE_SEC_UA
```

El correo no es decorativo: la SEC pide un user-agent que identifique a quien pregunta, y es la
condición para que el acceso sea legítimo.

## 4 · Llevar la base de datos — el paso delicado

**358 MB, 2.454.512 filas, esquema v7.** Está en la máquina de trabajo, en
`%APPDATA%\MirandasGroup\market.db`.

**No copiar el fichero en caliente.** Es una base en modo WAL: parte de su estado vive en el
`-wal`, y una copia cruda puede salir rota pareciendo perfecta. Hay que sacarla por el backup en
línea de SQLite, que es lo que hace `store backup`.

En la máquina de trabajo (Windows), con la app cerrada:

```powershell
.venv\Scripts\python.exe -X utf8 -m miratrade.cli store backup --force
# deja un zip en %APPDATA%\MirandasGroup\backups\miratrade-AAAAMMDD.zip
```

Ese zip lleva `market.db`, `practice.json`, `settings.json` y los reportes. Copiarlo al contenedor
y restaurarlo:

```bash
pct push 210 miratrade-AAAAMMDD.zip /tmp/mt.zip
pct exec 210 -- bash -lc '
  set -e
  install -d -o miratrade -g miratrade /opt/miratrade/restore
  cd /opt/miratrade/restore && unzip -o /tmp/mt.zip
  install -o miratrade -g miratrade -m 640 market.db /opt/miratrade/data/MirandasGroup/market.db
  install -d -o miratrade -g miratrade /opt/miratrade/app
  [ -f practice.json ] && install -o miratrade -g miratrade -m 640 practice.json /opt/miratrade/app/
  [ -f settings.json ] && install -o miratrade -g miratrade -m 640 settings.json /opt/miratrade/app/
  [ -d reports ] && cp -r reports/. /opt/miratrade/reports/ && chown -R miratrade:miratrade /opt/miratrade/reports
  rm -rf /opt/miratrade/restore /tmp/mt.zip
'
```

Comprobar que llegó entera antes de seguir:

```bash
pct exec 210 -- sudo -u miratrade /opt/miratrade/venv/bin/python -X utf8 \
  -m miratrade.cli store info
```

Tiene que decir **esquema v7** y unos 2,45 millones de filas. Si dice menos, parar y repetir el
paso: seguir con una base incompleta es peor que no desplegar.

## 5 · Servicios

```bash
pct exec 210 -- bash /opt/miratrade/src/deploy/systemd/instalar.sh
```

Instala tres cosas:

| Unidad | Qué hace |
|---|---|
| `miratrade-web.service` | la API y la web, en `127.0.0.1:8787` |
| `miratrade-scan.timer` | descarga mientras Nueva York presenta, y a las 23:00 |
| `miratrade-backup.timer` | la copia diaria, a las 04:30 |

El temporizador de descarga es seguro aunque dispare a menudo: mira primero la tabla `coverage` y
pide **solo los días laborables sobre los que nadie ha preguntado nunca**. Cuando no falta nada,
no cuesta nada.

El instalador termina llamando a `/api/health`. Si responde con el esquema y los contadores, el
servicio está bien.

## 6 · Túnel y acceso

`deploy/cloudflared/LEEME.md` tiene los comandos.

**Poner Cloudflare Access antes de publicar el DNS.** Sin esa política, ese hostname es la base de
datos entera en internet.

---

## Comprobaciones finales

```bash
pct exec 210 -- systemctl list-timers --no-pager 'miratrade-*'
pct exec 210 -- curl -fsS http://127.0.0.1:8787/api/health
pct exec 210 -- curl -fsS http://127.0.0.1:8787/api/honesty
```

Y desde fuera, en un navegador, el hostname del túnel: debe pedir el correo de Access primero.

## Lo que hay que devolver a la sesión de MiraTrade

1. La IP del contenedor y si la llave quedó puesta.
2. La salida de `store info` tras la restauración.
3. Lo que haya dicho `journalctl -u ssh` si la llave sigue sin funcionar.
4. Cualquier cosa del entorno que no coincida con lo escrito aquí — el almacenamiento, el puente
   de red, la plantilla. Eso es conocimiento de la red local y esta sesión no lo tiene.

## Lo que queda pendiente después

En `docs/PENDIENTE.md`. Relevante para el servidor: los temporizadores sustituyen a las tareas de
Windows (`miratrade schedule install` las imprime allí), y los secretos que hoy están en el
Administrador de credenciales de Windows tendrán que pasar a `systemd-creds` cuando haga falta
alguno en el servidor — hoy no hace falta ninguno, porque la web no habla con el bróker.

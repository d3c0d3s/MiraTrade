# Traspaso: desplegar MiraTrade en Odin

Para la sesión que tiene acceso a la red local. La sesión de MiraTrade no puede llegar a Odin: el
puerto es **9922** y responde, pero ninguna de las llaves de la máquina de trabajo está en
`authorized_keys`, y tras cuatro intentos la limitación de tasa empezó a cortar las conexiones.

Todo está en el repositorio, en `deploy/`. No hay que inventar nada: hay que ejecutarlo en orden y
comprobar lo que se dice al final de cada paso.

- Repo: `https://github.com/d3c0d3s/MiraTrade`
- Rama: `claude/swing-trades-analysis-fjb9lo`, commit `c47193e` o posterior

## Los datos de esta instalación

| | |
|---|---|
| Contenedor | **CT 150210** · 10 GB RAM · 4 núcleos · 50 GB disco |
| Red | `192.168.150.210/24` · gw `192.168.150.254` · DNS `192.168.150.101` · dominio `miratechcloud.com` |
| Hostname público | `miratrade.srv.miratechcloud.com` — **el registro DNS ya existe** |
| Túnel | **CT 150253** (`192.168.150.253`), cloudflared ya instalado ahí |

La convención de la red es que el **CTID son los dos últimos octetos de la IP**. Los números de
arriba no son arbitrarios y tienen que moverse juntos.

## Qué es esto y qué no

MiraTrade descarga presentaciones del SEC, precios y cadenas de opciones, las guarda en un SQLite y
las enseña. Lo que se despliega es **la API y la web**, que sustituyen a la app de escritorio.

Tres cosas que el código ya obliga y que no hay que aflojar:

1. **No envía órdenes.** Ni por esta vía ni por ninguna. Las credenciales del bróker y la decisión
   de operar se quedan en la máquina de la persona.
2. **Ninguna lectura descarga.** Un refresco de página no puede convertirse en una petición al SEC.
   Descargar ocurre cuando alguien lo pide, como trabajo con estado visible.
3. **La API verifica el token de Cloudflare Access**, y **se niega a arrancar** escuchando fuera de
   loopback si Access no está configurado. Eso no es un aviso: es un `SystemExit`.

---

## 0 · Antes del despliegue: rotar la contraseña de root de Proxmox

No es parte del despliegue. Es más urgente que él.

La contraseña actual está **en texto plano en 43 ficheros** de la máquina de trabajo: transcritos de
Claude de cuatro proyectos, ficheros de memoria, reglas de permisos en `settings.local.json`, y
—lo peor— ficheros `.env` y `prod.env` de despliegue de RippedAndRenew, más un `DEPLOY_GUIDE.md`.

Comprobado: **ninguno está seguido por git**, así que no se ha publicado. Pero los `.env` son
ficheros que se despliegan, así que conviene mirar si acabó también en el hosting de RippedAndRenew.

```bash
passwd root
```

Rotarla vuelve inofensivas las 43 copias de una vez. Perseguirlas una a una no es realista: ya
aparecieron en sitios que nadie habría mirado.

---

## 1 · Crear el contenedor

**En el nodo Proxmox, como root.**

```bash
git clone -b claude/swing-trades-analysis-fjb9lo https://github.com/d3c0d3s/MiraTrade /tmp/mt
cd /tmp/mt

# Una llave pública por línea: las que deban poder entrar AL CONTENEDOR.
# La de la máquina de trabajo, si se quiere que esa sesión pueda operarlo después:
#   ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMqgdZmS3If27LasiBSGXie2vLqhE6ru+Odp7bSczOor ladmin@mirandasgroup.com
# Es UNA SOLA LÍNEA. Si el copiado la parte en dos, sshd la ignora en silencio.
vi /root/.ssh/miratrade_authorized_keys

# Comprobar que la plantilla y el almacenamiento son los de esta máquina
pveam available | grep debian-12
pvesm status

bash deploy/lxc/crear-contenedor.sh
```

El script **se niega a continuar** si el CTID ya existe, si falta la plantilla o si no hay fichero
de llaves. Además escribe `/etc/pve/firewall/150210.fw` con `policy_in: DROP` y el **8787 abierto
solo a `192.168.150.253`**. La API verifica el token de Access; esto es la otra cerradura de la
misma puerta, la que no depende de que el código acierte.

Para que esa regla aplique, el cortafuegos del datacenter tiene que estar activo:

```bash
pvesh get /cluster/firewall/options
```

## 2 · Preparar el contenedor

```bash
pct push 150210 /tmp/mt/deploy/lxc/preparar.sh /root/preparar.sh
pct exec 150210 -- bash /root/preparar.sh
```

Instala Python y las dependencias, crea el usuario de servicio `miratrade` en `/opt/miratrade`,
clona el repo, monta el venv y escribe `/etc/miratrade.env`.

**También instala FinBERT** (extra `news`) y descarga el modelo con la consola delante, en vez de
la primera vez que alguien pulse el interruptor desde el móvil y se quede mirando una pantalla
quieta cuatro minutos. Son ~250 MB de ONNX Runtime y ~440 MB de modelo. Para saltarlo:
`WITH_NEWS=0 bash /root/preparar.sh`.

El ajuste viene **apagado** de todas formas: ninguna señal de noticias de este proyecto ha
sobrevivido a una prueba fuera de muestra, así que la aplicación funciona igual sin él.

Luego, a mano:

```bash
pct exec 150210 -- vi /etc/miratrade.env
```

- `MIRATRADE_SEC_UA` → **un correo real tuyo**. La SEC pide un user-agent que identifique a quien
  pregunta, y es la condición para que el acceso sea legítimo.
- `MIRATRADE_ACCESS_TEAM` → el nombre de tu equipo de Cloudflare Zero Trust (el de
  `<equipo>.cloudflareaccess.com`).
- `MIRATRADE_ACCESS_AUD` → el *Application Audience tag* de la aplicación de Access. Se obtiene en
  el paso 5, así que lo normal es volver aquí.

**Sin esas dos últimas, el servicio no arranca.** Es deliberado.

## 3 · Llevar la base de datos — el paso delicado

**375 MB, unos 2,5 millones de filas, esquema v8.** Está en la máquina de trabajo, en
`%APPDATA%\MirandasGroup\market.db`.

**No copiar el fichero en caliente.** Es una base en modo WAL: parte de su estado vive en el `-wal`
y una copia cruda puede salir rota pareciendo perfecta. Tiene que salir por el backup en línea de
SQLite, que es lo que hace `store backup`.

En la máquina de trabajo, con la app cerrada:

```powershell
.venv\Scripts\python.exe -X utf8 -m miratrade.cli store backup --force
```

Deja un zip en `%APPDATA%\MirandasGroup\backups\` con `market.db`, `practice.json`,
`settings.json` y los reportes. Copiarlo y restaurarlo:

```bash
pct push 150210 miratrade-AAAAMMDD.zip /tmp/mt.zip
pct exec 150210 -- bash -lc '
  set -e
  apt-get install -y -qq unzip
  install -d -o miratrade -g miratrade /opt/miratrade/restore
  cd /opt/miratrade/restore && unzip -o /tmp/mt.zip
  install -o miratrade -g miratrade -m 640 market.db /opt/miratrade/data/MirandasGroup/market.db
  [ -f practice.json ] && install -o miratrade -g miratrade -m 640 practice.json /opt/miratrade/app/
  [ -f settings.json ] && install -o miratrade -g miratrade -m 640 settings.json /opt/miratrade/app/
  [ -d reports ] && cp -r reports/. /opt/miratrade/reports/ && chown -R miratrade:miratrade /opt/miratrade/reports
  rm -rf /opt/miratrade/restore /tmp/mt.zip
'
```

Comprobar que llegó entera **antes** de seguir:

```bash
pct exec 150210 -- sudo -u miratrade /opt/miratrade/venv/bin/python -X utf8 \
  -m miratrade.cli store info
```

Tiene que decir **esquema v8** y unos 2,5 millones de filas. Si dice menos, parar y repetir: seguir
con una base incompleta es peor que no desplegar.

## 4 · Servicios

```bash
pct exec 150210 -- bash /opt/miratrade/src/deploy/systemd/instalar.sh
```

| Unidad | Qué hace |
|---|---|
| `miratrade-web.service` | la API y la web |
| `miratrade-scan.timer` | descarga mientras Nueva York presenta, y a las 23:00 |
| `miratrade-backup.timer` | la copia diaria, a las 04:30 |

El temporizador de descarga es seguro aunque dispare a menudo: mira primero la tabla `coverage` y
pide **solo los días laborables sobre los que nadie ha preguntado nunca**. Cuando no falta nada, no
cuesta nada.

**Un cambio necesario en la unidad web.** Viene configurada para escuchar en `127.0.0.1`, que es lo
correcto cuando el túnel está en la misma máquina. Aquí el túnel está en el CT 150253, así que
tiene que escuchar en la IP del contenedor:

```bash
pct exec 150210 -- sed -i 's/--host 127.0.0.1/--host 192.168.150.210/' \
  /etc/systemd/system/miratrade-web.service
pct exec 150210 -- sed -i '/^IPAddressAllow=/d' /etc/systemd/system/miratrade-web.service
pct exec 150210 -- systemctl daemon-reload
pct exec 150210 -- systemctl restart miratrade-web
```

En cuanto se haga eso, **el servicio exige Access**: sin `MIRATRADE_ACCESS_TEAM` y
`MIRATRADE_ACCESS_AUD` saldrá con

```
Refusing to listen on 192.168.150.210 without Cloudflare Access.
```

y no arrancará. Por eso el paso 5 va antes de reiniciar, o se reinicia dos veces.

## 5 · Túnel y acceso — en el CT 150253

cloudflared ya está instalado ahí. Solo hay que añadir el destino al túnel existente y crear la
política de Access. **La política primero.**

**Cloudflare Zero Trust → Access → Applications → Add → Self-hosted:**

- Dominio: `miratrade.srv.miratechcloud.com`
- Política: *Allow*, por tu correo (o por el grupo de tu IdP, si ya está Authentik/Entra detrás)
- Guardar, y **copiar el `Application Audience (AUD) Tag`** → ese es `MIRATRADE_ACCESS_AUD`
- El nombre del equipo, el de `<equipo>.cloudflareaccess.com`, es `MIRATRADE_ACCESS_TEAM`

**Después, el ingress.** En `/etc/cloudflared/config.yml` del CT 150253, añadir **antes** de la
regla final `http_status:404`:

```yaml
  - hostname: miratrade.srv.miratechcloud.com
    service: http://192.168.150.210:8787
    originRequest:
      connectTimeout: 30s
```

```bash
pct exec 150253 -- cloudflared tunnel ingress validate
pct exec 150253 -- systemctl restart cloudflared
```

El registro DNS ya existe, así que no hace falta `tunnel route dns`.

---

## 6 · Opcional: puntuar los 8-K con FinBERT

Nada de esto hace falta para que MiraTrade funcione. Es una medición pendiente, y el ajuste viene
apagado precisamente porque todavía no ha dado nada.

```bash
pct exec 150210 -- sudo -u miratrade /opt/miratrade/venv/bin/python -X utf8   -m miratrade.cli news status
```

Dice cuántas presentaciones haría falta puntuar. **Son unas 20.000**, y esa cifra sorprende: 2.900
están alrededor de eventos y el resto alrededor de los días placebo. Sin ese segundo lado no hay
comparación, y una tasa sin nada contra lo que medirse solo puede darse la razón a sí misma — que
es exactamente como salió mal la primera versión de este estudio.

Para encenderlo y puntuar:

```bash
# el ajuste vive en la base de datos, no en un fichero
pct exec 150210 -- sudo -u miratrade /opt/miratrade/venv/bin/python -X utf8   -m miratrade.cli store settings --set sentiment.enabled=true

# una prueba corta primero, para ver que el modelo carga
pct exec 150210 -- sudo -u miratrade /opt/miratrade/venv/bin/python -X utf8   -m miratrade.cli news score --limit 50

# y luego todo. Son horas de CPU; se puede interrumpir y continúa donde iba.
pct exec 150210 -- sudo -u miratrade /opt/miratrade/venv/bin/python -X utf8   -m miratrade.cli news score
```

La descarga va a ~7 documentos/s dentro del presupuesto del SEC, y la mediana de prosa utilizable
por documento es de **323 palabras** — medido sobre los 2.899 que ya se bajaron, con 0 fallos y 0
documentos que fueran solo formulario.

Después:

```bash
pct exec 150210 -- sudo -u miratrade /opt/miratrade/venv/bin/python -X utf8   -m miratrade.cli news study
```

Compara la redacción alrededor de los eventos con la de días placebo **en la misma fase del
trimestre**, y parte la ventana en dos para ver si lo que aparece en la primera mitad sigue ahí en
la segunda. Sin ese control, cualquier puntuación de sentimiento redescubre la ventana en la que
los directivos pueden comprar, disfrazada de noticia: es lo que pasó con los códigos de item.

---

## Comprobaciones finales

```bash
# desde el CT del túnel: debe responder
pct exec 150253 -- curl -fsS http://192.168.150.210:8787/api/health

# desde cualquier otro sitio de la red: NO debe responder (el cortafuegos)
pct exec 150210 -- systemctl is-active miratrade-web
pct exec 150210 -- systemctl list-timers --no-pager 'miratrade-*'
```

Y desde un navegador, `https://miratrade.srv.miratechcloud.com`: **tiene que pedir el correo de
Access primero**. Si entra directo, la política no está puesta y la base de datos está en internet.

Una prueba que merece hacerse una vez: pedir la misma URL con `curl` sin pasar por Access. Debe
devolver **403**, no la página.

## Lo que hay que devolver a la sesión de MiraTrade

1. Si la llave quedó puesta en el contenedor.
2. La salida de `store info` tras la restauración.
3. El `AUD tag` no — ese se queda en el contenedor.
4. Lo que haya dicho `journalctl -u ssh` si la llave sigue sin funcionar, y cualquier cosa del
   entorno que no coincida con lo escrito aquí. Eso es conocimiento de la red local y esta sesión
   no lo tiene.

## Después

`docs/PENDIENTE.md`. Para el servidor: los temporizadores sustituyen a las tareas de Windows, y los
secretos que hoy están en el Administrador de credenciales tendrán que pasar a `systemd-creds`
cuando haga falta alguno — hoy no hace falta ninguno, porque la web no habla con el bróker.

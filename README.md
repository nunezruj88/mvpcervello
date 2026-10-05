# MVP Cervelló

Web para un LXC: **http://10.8.1.106:8083**. Código independiente en `/var/www/mvp-cervello`, datos en `/var/lib/mvp-cervello/mvp.sqlite3`, servicio propio y backend privado `127.0.0.1:8092`.

## Qué puedes hacer

- Cargar `.xlsx` (primera hoja, valores sin fórmulas) o `.csv` con las columnas del archivo generado a partir del vídeo. Revisión antes de guardar, validación y reemplazo transaccional por partido. Los archivos no se publican.
- Consultar todos los partidos o uno concreto. Puntos por jugador y período, tiros libres/de 2/de 3, faltas y acciones.
- Seleccionar equipo y jugador en la parte superior. Los equipos y jugadores aparecen al importar sus partidos, incluidos partidos sin MVP Cervelló. Cada equipo muestra sus partidos y estadísticas. La exportación incluye las acciones de ambos equipos de los partidos seleccionados, para conservar el partido al reimportarlo.
- Seguir a M.N.L. y a cualquier otro jugador en varios equipos, seleccionando cada equipo por separado. Se identifica por el nombre normalizado, nunca solo por el dorsal; M.N.L. y MNL se reconocen como el mismo nombre. Usa un nombre consistente y distinto para cada persona en los archivos. No se unen automáticamente alias diferentes ni se distinguen dos personas con el mismo nombre. Los dorsales pueden variar entre partidos.
- Guardar los partidos en el servidor y exportar sus acciones a CSV. Los datos persisten entre reinicios y son compartidos por todos los usuarios autorizados.

No convierte vídeos automáticamente. Primero se extrae el vídeo en el chat; después se sube el archivo resultante. Incluye un ejemplo con nombres ficticios en `examples/`, **no cargado automáticamente**. Los archivos reales y la base de datos permanecen fuera del repositorio.

## Cobertura y cálculos

Por defecto, cada importación es parcial. Marca «partido completo» únicamente si el archivo contiene todas las acciones. Esta marca es una declaración del usuario, no una comprobación automática de la grabación. No hay victorias, clasificación ni promedios de partido completo a partir de fragmentos.

Los puntos se suman por acción. No se suman los marcadores de las tarjetas (son por período). El ordinal «1a falta» no se suma: se cuenta una falta por acción. Los porcentajes usan canastas e intentos fallados explícitos. Sin intentos, se muestra «—». La ausencia de acciones de rebote, asistencia, etc. no prueba un total real de cero; la interfaz prioriza puntos, tiros y faltas registrados. Los tipos no reconocidos se conservan y se avisan en la revisión.

Un archivo corresponde a un partido (fecha + local + visitante). La ordenación de jugadas conserva el orden del archivo. Los fragmentos deben unirse y eliminar solapamientos antes de importarlos. Reimportar reemplaza el partido completo, no añade sus acciones. Las acciones idénticas se avisan pero se conservan porque dos tiros libres fallados al mismo tiempo pueden ser legítimos. Importar parcialmente sobre un partido completo reduce la cobertura si se confirma el reemplazo.

CSV: UTF-8/BOM o Windows-1252, separador coma, punto y coma o tabulación. Máximo 10 MB y 20.000 registros. Fecha `AAAA-MM-DD` o `DD/MM/AAAA`, período `P1`, tiempo restante `MM:SS`. Las cabeceras obligatorias son `Fecha_partido`, `Local`, `Visitante`, `Periodo`, `Tiempo_restante`, `Equipo`, `Dorsal`, `Jugador`, `Accion_original`, `Puntos_accion`. El resto es opcional. La plantilla descargable contiene cabecera y una fila de ejemplo; elimina esa fila para tu archivo real. Los valores originales de marcadores no se utilizan para cálculos ni se conservan en la exportación; el dato autorizado son los puntos de cada acción.

## Equipo y categoría en el fichero

- `Equipo` identifica al club de la acción: por ejemplo, `CB BEGUES` o `MVP CERVELLÓ`. Debe coincidir con `Local` o `Visitante`.
- `Categoria_equipo` identifica la categoría de esa acción, por ejemplo `Mini masculí`. Es opcional y se conserva por fila en SQLite al confirmar la importación, se muestra en la revisión y se incluye al exportar CSV.
- Si falta la columna o su valor está vacío, se guarda una categoría vacía. Los partidos antiguos siguen siendo compatibles; para incorporar la categoría a sus acciones debes reimportar el fichero corregido y confirmar el reemplazo.
- No renombres `Categoria_equipo` como `Equipo`: las dos columnas tienen significados distintos. Si ya hay dos cabeceras `Equipo`, renombra la última (la que contiene `Mini masculí`) a `Categoria_equipo`.
- La categoría se conserva como dato de cada acción; los selectores actuales filtran por club y jugador, no por categoría.

Ejemplo de cabecera y fila válidas:

```csv
Orden;Fecha_partido;Local;Visitante;Periodo;Tiempo_restante;Equipo;Dorsal;Jugador;Accion_original;Puntos_Begues_periodo;Puntos_Cervello_periodo;Puntos_accion;Observaciones;Categoria_equipo
1;2026-10-03;CB BEGUES;MVP CERVELLÓ;P1;06:00;CB BEGUES;5;JUGADOR 5;Salt guanyat;0;0;0;;Mini masculí
```

## Instalar en el LXC

Ejecuta los pasos siguientes como `root` dentro del LXC. Comprueba que ambos puertos están libres:

```sh
ss -ltnp 'sport = :8083'
ss -ltnp 'sport = :8092'
nginx -t
```

Si alguno está ocupado, elige otro antes de instalar y ajusta la configuración y la URL. Para una primera instalación:

```sh
apt-get update
apt-get install -y git ca-certificates python3-venv apache2-utils curl
test ! -e /var/www/mvp-cervello || { echo 'La carpeta ya existe. Revisar antes de instalar.'; exit 1; }
test ! -e /etc/nginx/sites-available/mvp-cervello || { echo 'El sitio ya existe.'; exit 1; }
test ! -e /etc/nginx/sites-enabled/mvp-cervello || { echo 'El sitio ya está activado.'; exit 1; }
useradd --system --home /var/lib/mvp-cervello --shell /usr/sbin/nologin mvp-cervello
git clone --branch main https://github.com/nunezruj88/mvpcervello.git /var/www/mvp-cervello
python3 -m venv /var/www/mvp-cervello/.venv
/var/www/mvp-cervello/.venv/bin/pip install -r /var/www/mvp-cervello/requirements.txt
cp /var/www/mvp-cervello/deploy/mvp-cervello.service /etc/systemd/system/mvp-cervello.service
systemctl daemon-reload
systemctl enable --now mvp-cervello
curl --fail http://127.0.0.1:8092/health
```

Crear una contraseña propia para esta web (usuario `administrador`). El comando pide la contraseña; no la pongas en un archivo ni en el chat. Si ya existe el fichero, no utilizar `-c`.

```sh
test ! -f /etc/nginx/mvp-cervello.htpasswd && htpasswd -c /etc/nginx/mvp-cervello.htpasswd administrador
chown root:www-data /etc/nginx/mvp-cervello.htpasswd
chmod 640 /etc/nginx/mvp-cervello.htpasswd
cp /var/www/mvp-cervello/deploy/mvp-cervello.nginx.conf /etc/nginx/sites-available/mvp-cervello
ln -s /etc/nginx/sites-available/mvp-cervello /etc/nginx/sites-enabled/mvp-cervello
nginx -t && systemctl reload nginx
curl -I http://127.0.0.1:8083/
curl --fail -u administrador http://127.0.0.1:8083/health
```

La primera petición devuelve 401; la segunda, tras la contraseña, `{"status":"ok"}`. Abre **http://10.8.1.106:8083** y sube tu archivo extraído del vídeo, dejándolo parcial si no contiene todo el partido. El backend 8092 no se expone a la red. Si hay firewall, permitir solo 8083 desde tu LAN real. Esta configuración es para tu red local; no incluye publicación externa ni cambios de Tunnel.

## Actualizar y respaldar

La base de datos y el fichero de contraseñas están fuera del repositorio. No vuelvas a ejecutar los pasos de primera instalación sobre una existente. Para actualizar, comprueba primero que no haya modificaciones locales:

```sh
cd /var/www/mvp-cervello
git status --short
```

Si no aparece ningún archivo modificado:

```sh
git pull --ff-only origin main &&
.venv/bin/pip install -r requirements.txt &&
systemctl restart mvp-cervello
curl --fail http://127.0.0.1:8092/health
```

Si hay cambios locales, consérvalos y revisa antes de actualizar. Después de actualizar, recarga el navegador. Los cambios futuros en los archivos de `deploy/` requieren revisar y copiar las nuevas configuraciones por separado.

Copia de seguridad consistente con el servicio detenido:

```sh
systemctl stop mvp-cervello
cp -a /var/lib/mvp-cervello/mvp.sqlite3 /var/lib/mvp-cervello/mvp.backup.sqlite3
systemctl start mvp-cervello
```

Para pruebas locales: Python 3.10+, instalar `openpyxl` y ejecutar `python app.py`. Escucha solo en `127.0.0.1:8092`. Pruebas de importación, persistencia y cálculos: `python -m unittest discover -s tests -v`. Gunicorn se utiliza en Linux, no en Windows.

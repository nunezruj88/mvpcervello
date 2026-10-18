# MVP Cervelló

Web para un LXC: **http://10.8.1.106:8083**. Código independiente en `/var/www/mvp-cervello`, datos en `/var/lib/mvp-cervello/mvp.sqlite3`, servicio propio y backend privado `127.0.0.1:8092`.

## Qué puedes hacer

- Cargar `.xlsx` (primera hoja, valores sin fórmulas) o `.csv` con las columnas del archivo generado a partir del vídeo. Revisión antes de guardar, validación y reemplazo transaccional por partido. Los archivos no se publican.
- Consultar todos los partidos o uno concreto. Puntos por jugador y período, tiros libres/de 2/de 3, faltas y acciones.
- Seleccionar la categoría del MVP Cervelló y uno de los jugadores M.N.L. o E.L.N. en la parte superior. Los partidos, estadísticas y exportación se filtran por las categorías y partidos del jugador seleccionado; las acciones de los rivales no se suman a las estadísticas del MVP Cervelló. La vista de equipo muestra todos sus jugadores; el seguimiento individual utiliza los jugadores presentes en los datos importados.
- Seguir a M.N.L. y E.L.N. en las distintas categorías del MVP Cervelló, seleccionando cada categoría por separado. Se identifica por el nombre normalizado, nunca solo por el dorsal; M.N.L. y MNL se reconocen como el mismo nombre. Usa un nombre consistente y distinto para cada persona en los archivos. No se unen automáticamente alias diferentes ni se distinguen dos personas con el mismo nombre. Los dorsales pueden variar entre partidos.
- Guardar los partidos en el servidor y exportar sus acciones a CSV. Los datos persisten entre reinicios y son compartidos por todos los usuarios autorizados.

No convierte vídeos automáticamente. Primero se extrae el vídeo en el chat; después se sube el archivo resultante. Incluye un ejemplo con nombres ficticios en `examples/`, **no cargado automáticamente**. La base de datos permanece fuera del repositorio. Los ficheros importados se conservan en la carpeta privada `partidos/`, excluida de Git.

## Cobertura y cálculos

Por defecto, cada importación es parcial. Marca «partido completo» únicamente si el archivo contiene todas las acciones. Esta marca es una declaración del usuario, no una comprobación automática de la grabación. No hay victorias, clasificación ni promedios de partido completo a partir de fragmentos.

Los puntos se suman por acción. No se suman los marcadores de las tarjetas (son por período). El ordinal «1a falta» no se suma: se cuenta una falta por acción. Los porcentajes usan canastas e intentos fallados explícitos. Sin intentos, se muestra «—». La ausencia de acciones de rebote, asistencia, etc. no prueba un total real de cero; la interfaz prioriza puntos, tiros y faltas registrados. Los tipos no reconocidos se conservan y se avisan en la revisión.

Un archivo corresponde a un partido (fecha + local + visitante + categoría del MVP Cervelló, si existe). La ordenación de jugadas conserva el orden del archivo. Los fragmentos deben unirse y eliminar solapamientos antes de importarlos. Reimportar reemplaza el partido completo, no añade sus acciones. Las acciones idénticas se avisan pero se conservan porque dos tiros libres fallados al mismo tiempo pueden ser legítimos. Importar parcialmente sobre un partido completo reduce la cobertura si se confirma el reemplazo.

CSV: UTF-8/BOM o Windows-1252, separador coma, punto y coma o tabulación. Máximo 10 MB y 20.000 registros. Fecha `AAAA-MM-DD` o `DD/MM/AAAA`, período `P1`, tiempo restante `MM:SS`. Las cabeceras obligatorias son `Fecha_partido`, `Local`, `Visitante`, `Periodo`, `Tiempo_restante`, `Equipo`, `Dorsal`, `Jugador`, `Accion_original`, `Puntos_accion`. El resto es opcional. La plantilla descargable contiene cabecera y una fila de ejemplo; elimina esa fila para tu archivo real. Los valores originales de marcadores no se utilizan para cálculos ni se conservan en la exportación; el dato autorizado son los puntos de cada acción.

## Equipo y categoría en el fichero

- `Equipo` identifica al club de la acción: por ejemplo, `CB BEGUES` o `MVP CERVELLÓ`. Debe coincidir con `Local` o `Visitante`.
- `Categoria_equipo` identifica la categoría de esa acción, por ejemplo `Mini masculí`. Es opcional y se conserva por fila en SQLite al confirmar la importación, se muestra en la revisión y se incluye al exportar CSV.
- Si falta la columna o su valor está vacío, se guarda una categoría vacía. Los partidos antiguos siguen siendo compatibles; para incorporar la categoría a sus acciones debes reimportar el fichero corregido y confirmar el reemplazo.
- No renombres `Categoria_equipo` como `Equipo`: las dos columnas tienen significados distintos. Si ya hay dos cabeceras `Equipo`, renombra la última (la que contiene `Mini masculí`) a `Categoria_equipo`.
- El selector principal usa `Categoria_equipo` de las acciones del MVP Cervelló, no el nombre del rival. Los registros antiguos o vacíos aparecen como «Sin categoría». M.N.L. y E.L.N. se seleccionan por separado y se identifican por nombre, no por dorsal.
- Un fichero debe contener una sola categoría del MVP Cervelló. Usa esa categoría en todas las filas de sus acciones. La categoría forma parte de la identidad del partido: dos categorías con la misma fecha y clubes no se reemplazan entre sí. Al reimportar con categoría un partido antiguo sin categoría, se pide confirmar el reemplazo y se actualiza el registro antiguo en la misma transacción.

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
install -d -o mvp-cervello -g mvp-cervello -m 700 /var/www/mvp-cervello/partidos
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

## Competición en el fichero

Las columnas opcionales `Competicion` y `Fecha_competicion` identifican la competición y su fecha de inicio. Usa ambas juntas, con fecha AAAA-MM-DD o DD/MM/AAAA (también una fecha de Excel). Basta indicarlas en una fila; los valores no vacíos deben coincidir en todo el partido. Se conservan al guardar y exportar. No cambian la identidad del partido: reimportar el fichero actualizado requiere confirmar el reemplazo.

Los selectores de partido del equipo y del jugador agrupan los partidos bajo «DD/MM/AAAA - Competición», ordenados por fecha de inicio. Dos ediciones con el mismo nombre y fechas distintas forman grupos separados. Los partidos antiguos o sin esos datos aparecen en «Sin competición»; reimpórtalos para asignarles una competición.

Dentro de cada grupo puedes seleccionar «Toda la competición» para ver las estadísticas acumuladas de sus partidos, respetando categoría y jugador. La exportación utiliza la misma selección. Estas son las métricas actuales; las métricas específicas de temporada están pendientes de definir. Al seleccionar un partido concreto, la tarjeta «Partidos importados» se sustituye por el marcador local/visitante calculado sumando los puntos de las acciones importadas de cada equipo. Los partidos parciales se identifican como «Marcador parcial»; no se suman los marcadores por período de las tarjetas originales.


## Selección de datos

Los tres selectores superiores siguen la relación Jugador → Categoría → Competición → Partido. Jugador ofrece únicamente M.N.L. y E.L.N. cuando tienen registros del MVP Cervelló. Categoría ofrece únicamente las categorías con registros de ese jugador. Competición es el agrupador del selector Partido y contiene únicamente sus partidos en la categoría elegida. Puede elegirse toda una competición o un partido concreto. La selección se comparte entre las vistas del equipo y del jugador; la vista del equipo muestra a todos los jugadores de los partidos seleccionados. Si una selección deja de ser válida al cambiar un filtro, se ajusta automáticamente. Los datos existentes se conservan: no hace falta borrar ni migrar la base de datos.


## Minutos jugados

Se calculan al consultar los datos ya guardados, sin migrar SQLite ni reimportar si las acciones ya están presentes. Se muestran en la tabla de jugadores y en el seguimiento individual.

- `Entra al camp` y `Surt del camp` delimitan intervalos por jugador y período; también se procesan las entradas iniciales de P1. Los relojes representan tiempo restante.
- La duración usa `period_seconds` del partido (obtenida de la primera fila al importar); en datos antiguos se usa el reloj de esa primera fila. El fichero debe empezar con la duración real del período: no se fija una duración por categoría ni se incluyen descansos.
- Una entrada al inicio confirma al titular. Una salida aislada no permite suponer desde cuándo estaba jugando. El estado conocido se mantiene entre períodos consecutivos; una entrada a la duración inicial puede reafirmarlo.
- Una entrada abierta se cierra a cero solo cuando consta el fin del período, existe un período posterior o el partido está marcado como completo. Si falta ese límite no se inventa una salida.
- Los intervalos cerrados y confirmados se conservan aunque otras partes no se puedan calcular. Se muestran como `MM:SS (incompletos)` si el archivo es parcial, faltan períodos, hay cambios ausentes o duplicados, o relojes inconsistentes; `— (incompletos)` indica que no hay tiempo confirmado. La explicación aparece al situar el cursor sobre el valor.
- Los nombres se normalizan igual que en las estadísticas; no se identifica al jugador solamente por el dorsal. Una selección de varios partidos suma sus intervalos confirmados e indica si alguno tiene datos incompletos.

## Copias de los ficheros importados

Al confirmar y guardar una importación válida se conserva una copia exacta del CSV o Excel original en `/var/www/mvp-cervello/partidos`. Revisar un archivo, rechazarlo por errores o intentar duplicarlo sin confirmar el reemplazo no crea copias. Cada importación confirmada recibe un nombre único con fecha del partido, nombre saneado y sufijo aleatorio. Reemplazar los datos del partido conserva las versiones originales anteriores.

Los permisos de la carpeta son `700` y los de cada archivo `600`, bajo el usuario del servicio. Los archivos no se sirven por HTTP y `partidos/` está excluido de Git. Guarda también esta carpeta en tus copias de seguridad: la copia de SQLite por sí sola no incluye los originales. Para otra ubicación usa `MVP_IMPORT_DIR`, ajustando también permisos y `ReadWritePaths` del servicio.

Si no se puede guardar la copia por falta de permisos o espacio, se rechaza la importación y se mantienen los datos anteriores. Si falla la escritura o confirmación de SQLite después de crear la copia, se retira esa nueva copia. Los partidos importados antes de esta actualización no tienen copia original; reimporta sus ficheros con reemplazo para archivarlos.

### Activar en una instalación existente

Como `root`, después de descargar los cambios:

```sh
cd /var/www/mvp-cervello
git pull --ff-only origin main
install -d -o mvp-cervello -g mvp-cervello -m 700 /var/www/mvp-cervello/partidos
cp deploy/mvp-cervello.service /etc/systemd/system/mvp-cervello.service
systemctl daemon-reload
systemctl restart mvp-cervello
curl --fail http://127.0.0.1:8092/health
```

El servicio utiliza `ProtectSystem=strict`; la nueva directiva `ReadWritePaths` permite escribir únicamente en esta carpeta adicional. No es necesario dar permisos de escritura a todo el proyecto. Si personalizaste el servicio, incorpora solo `Environment=MVP_IMPORT_DIR=/var/www/mvp-cervello/partidos` y `ReadWritePaths=/var/www/mvp-cervello/partidos` a tu configuración antes de recargarla.


## Clasificación oficial guardada

En **Estadísticas del equipo**, selecciona **Toda la competición · 01/10/2026 - Primera fase - Nivel C - 1** para ver la clasificación guardada en SQLite. La clasificación se actualiza importando una página HTML desde **Importar datos → Importar clasificación**. En la vista del equipo se lee la copia local; no hay botón de consulta externa. Se reconocen las variantes Nivel/Nivell y 1/01/10 para esta asociación. Abrir la página, cambiar de jugador/categoría/partido o reiniciar el servicio **nunca consulta la web externa**. No hay tareas programadas ni temporizadores de actualización.

La opción indicada se asocia expresamente a https://www.basquetcatala.cat/competicions/resultats/24222, que la federación identifica como **C.T. Pre-infantil Masculí · Primera fase · Nivel C · Grupo 10**. El nombre importado «Nivel C - 1» se mantiene; la tabla muestra el grupo real de la fuente para evitar confusiones. La opción **01/10/2026 - Primera fase - Nivel C - 11** se asocia a https://www.basquetcatala.cat/competicions/resultats/24360 (**C.T. Mini Masculí · Primera fase · Nivel C · Grupo 11**). Cada competición consulta su propia fuente y conserva su propia copia en SQLite. Otras competiciones necesitan una asociación propia.

La tabla muestra posición, equipo, partidos jugados, ganados, perdidos, no presentados, puntos a favor, puntos en contra y puntos de clasificación. Las copias se guardan en la tabla SQLite `standings`, separadas por categoría, fecha de competición y nombre de competición, independientemente del jugador. No se modifican las jugadas importadas.

`GET /api/standings` solo lee la copia local. La interfaz no envía peticiones de descarga de la clasificación a la federación. La carga y actualización se realizan mediante la importación manual de HTML, validada antes de guardar.

No requiere nuevas dependencias ni reimportar CSV. Actualización del LXC:

```bash
cd /var/www/mvp-cervello
git pull --ff-only origin main && systemctl restart mvp-cervello
```

## Importar datos: partidos y clasificaciones HTML

La sección antes llamada **Cargar partido** ahora se llama **Importar datos** y reúne las importaciones manuales. Mantiene la carga de partidos CSV/Excel y añade el formulario **Importar clasificación**.

1. Abre la clasificación oficial en tu navegador y guarda la página como HTML (`Ctrl+S`). Se admiten `.html` y `.htm`, hasta 10 MB. No hace falta subir la carpeta de recursos que pueda crear el navegador.
2. En **Importar datos → Importar clasificación**, elige la categoría y competición de destino. El formulario ofrece las competiciones configuradas presentes en los partidos guardados, independientemente del jugador y de los filtros superiores. Si no hay destinos, importa primero un partido con categoría, competición y fecha de competición.
3. Selecciona el HTML y pulsa **Revisar clasificación**. Se comprueban la categoría oficial y el grupo del archivo; la tabla muestra posición, equipos, partidos, victorias, derrotas, no presentados, PF, PC y puntos. Se conserva la jornada indicada en la página.
4. Pulsa **Guardar clasificación**. Si existe una clasificación para ese destino, confirma **Reemplazar**. La revisión no guarda datos ni crea copias.
5. En **Estadísticas del equipo**, selecciona esa categoría y **Toda la competición** para leer la clasificación guardada. La fecha mostrada corresponde al guardado; los resultados corresponden a la página que descargaste.

El formulario procesa solo el HTML subido: no ejecuta sus scripts, no abre enlaces, no carga recursos y no consulta la web. Guarda la tabla en SQLite y una copia exacta del HTML en `partidos/`, con nombre único; los reemplazos conservan los originales anteriores. Si falla la validación, el archivo o SQLite, se mantiene la clasificación anterior. La vista del equipo solo muestra los datos guardados; las actualizaciones se realizan mediante este formulario. No hay actualizaciones automáticas.

La importación de clasificaciones no modifica las acciones ni las estadísticas de los partidos. No requiere dependencias nuevas, migraciones manuales ni cambios de permisos si ya está habilitada la carpeta `partidos`. Las nuevas pruebas incluyen `python -m unittest discover -s tests`, `node tests/test_standings_frontend.cjs` y `node tests/test_standings_import_frontend.cjs`.

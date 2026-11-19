# PE-U1: comunicación entre procesos con sockets TCP y gRPC

Práctica experimental de la Unidad 1 (GA-SUM-01 / PE-U1) de Aplicaciones Distribuidas (ISR-701), Universidad Técnica Estatal de Quevedo, Carrera de Software, paralelo B. Cierre: domingo 22 de noviembre de 2026, 23:55.

Tres nodos en la misma máquina se comunican primero con sockets TCP y después con gRPC. Cada nodo lleva un reloj de Lamport. Medimos la latencia y el rendimiento de los dos mecanismos y comprobamos el orden de los eventos con los relojes.

| Integrante | GitHub | Parte del código |
|---|---|---|
| Benites Pérez Dariem Alberto | [DALBEZ-ROG](https://github.com/DALBEZ-ROG) | `src/comun/`, `src/ejecutar_experimento.py`, `analysis/` y `docs/` |
| Bueno Troya Erwin Daniel | [Troyano2004](https://github.com/Troyano2004) | `src/sockets/` |
| Mendoza Villarroel Elian Jossue | [Elianmen123](https://github.com/Elianmen123) | `proto/` y `src/grpc/` |

## Video

Pendiente.

## Nodos

| Nodo | Puerto | Papel en el diagrama de FORM-TL-01 |
|---|---|---|
| nodo-A | 5000 | cliente de reservas |
| nodo-B | 5001 | servidor de aplicación |
| nodo-C | 5002 | servicio de pagos |

Los 20 intercambios del escenario están en `src/comun/escenario.py`. Los pasos 1 y 2 salen a la vez desde nodo-A y nodo-C, por eso son eventos concurrentes.

## Carpetas

| Carpeta o archivo | Qué tiene |
|---|---|
| `src/comun/` | Configuración de los nodos, reloj de Lamport, escenario, registro en CSV y protocolo de medición que usan los dos mecanismos |
| `src/sockets/` | Nodo con sockets TCP: un servidor que recibe JSON `{sender, timestamp, message}` y un cliente con reloj de Lamport |
| `proto/` | `mensajeria.proto`: servicio `Mensajeria` con `rpc EnviarMensaje(Mensaje) returns (Acuse)` |
| `src/grpc/` | Nodo con gRPC y el código generado con grpcio-tools |
| `src/ejecutar_experimento.py` | Corre el protocolo experimental completo y deja los datos en `data/` |
| `data/` | CSV de eventos y de latencias sin editar, condiciones de la máquina, salida de cada proceso y `SHA256SUMS` |
| `analysis/` | Script de análisis y verificación de Lamport, con las tablas y gráficos que generan |
| `docs/` | Informe en LaTeX, bibliografía, capturas y el PDF compilado |
| `caratula/` | Carátula de una página para el SGA |

## Instalación

Python 3.11 o superior. Nosotros usamos Python 3.12.10 en Windows 11 con cmd.exe. Desde la raíz del repositorio:

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Si se cambia `proto/mensajeria.proto`, el código de gRPC se genera otra vez con:

```
src\grpc\generar_codigo.bat
```

Los nodos y el experimento se ejecutan con `python -m` desde la raíz del repositorio. Si se ejecuta un archivo que está dentro de `src/`, Python confunde la carpeta `src/grpc` con la librería `grpc`.

## Ejecutar los nodos

Los 20 intercambios con sockets, una consola por nodo:

```
python -m src.sockets.nodo A
python -m src.sockets.nodo B
python -m src.sockets.nodo C
```

Con gRPC es igual, con `src.grpc` en lugar de `src.sockets`. Cada nodo espera a los otros dos, hace sus envíos y recepciones y guarda sus eventos en `data/eventos_<mecanismo>_nodo-X.csv`.

Latencia de ida y vuelta (1 corrida de calentamiento y 5 corridas de 100 envíos, con mensajes de 100 y de 10 000 caracteres), en dos consolas:

```
python -m src.sockets.nodo B --modo receptor
python -m src.sockets.medir_latencia --emisor A --receptor B
```

Para pruebas que no deben mezclarse con los datos del experimento se agrega `--salida pruebas`. Esa carpeta no se sube al repositorio.

## Experimento completo

Con las demás aplicaciones cerradas:

```
python -m src.ejecutar_experimento --notas "qué más estaba abierto"
```

Para sockets y para gRPC hace tres pruebas: el escenario con los tres nodos, la latencia de nodo-A a nodo-B y la prueba con tres clientes a la vez (A→B, B→C y C→B). Guarda las condiciones de la máquina en `data/condiciones.json`, la salida de cada proceso en `data/logs/` y la huella SHA-256 de cada archivo en `data/SHA256SUMS`. Si en `data/` ya hay datos, no corre, a menos que se use `--sobrescribir`.

## Análisis

```
python analysis\analizar.py
python analysis\verificar_lamport.py
```

`analizar.py` revisa primero `SHA256SUMS`. Luego calcula, sin la corrida de calentamiento, la media, la mediana, la desviación estándar, el percentil 95 y los mensajes por segundo de cada mecanismo y tamaño, y genera las tablas de `analysis/tablas/` y los gráficos de `analysis/figuras/`.

`verificar_lamport.py` usa los CSV de eventos para comprobar que en los 20 mensajes el reloj al recibir es mayor que al enviar, y busca eventos concurrentes con el mismo valor de reloj.

Para revisar las huellas a mano, en Git Bash dentro de `data/`: `sha256sum -c SHA256SUMS`.

## Compilar el informe

Hace falta MiKTeX o TeX Live con `pdflatex` y `biber`. El archivo principal es `docs/main.tex`. Usa los paquetes `babel` (español), `fontenc`, `lmodern`, `geometry`, `graphicx`, `booktabs`, `float`, `caption`, `listings`, `csquotes`, `biblatex` con el estilo `biblatex-ieee`, `hyperref` y `xurl`.

```
cd docs
pdflatex main
biber main
pdflatex main
pdflatex main
```

Las tablas y los gráficos del informe se toman de `analysis/tablas/` y `analysis/figuras/`, así que primero hay que correr el análisis. El archivo `docs/main.bbl` se deja en el repositorio: si `biber` no está disponible, `pdflatex` usa ese archivo y las referencias salen igual.

La carátula se compila con una sola pasada de `pdflatex caratula` dentro de `caratula/`.

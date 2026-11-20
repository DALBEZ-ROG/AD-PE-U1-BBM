# Bitácora del equipo

## Miércoles 18 de noviembre de 2026

- **Presentes:** Dariem Benites.
- **Qué hicimos:**
  - Se leyó la guía de la PE-U1 y se repartió el trabajo: Erwin hace los sockets TCP (`src/sockets/`), Elian el gRPC (`proto/` y `src/grpc/`) y Dariem el código común, el script del experimento, el análisis y el informe.
  - Los tres nodos salen del diagrama de FORM-TL-01: nodo-A es el cliente de reservas, nodo-B el servidor de aplicación y nodo-C el servicio de pagos, en los puertos 5000, 5001 y 5002.
  - Se escribieron los 20 intercambios del escenario: consulta de vuelos, reserva, cobro, consulta del estado, cobro de equipaje rechazado, reintento con otra tarjeta y comprobantes. Los pasos 1 y 2 salen a la vez desde nodo-A y nodo-C para tener dos eventos concurrentes.
  - Se instaló Python 3.12.10 y las librerías de `requirements.txt`.
  - Se subió el código común: reloj de Lamport, configuración, escenario, registro en CSV y el protocolo de medición que usan los dos mecanismos.
  - Se creó el repositorio con el README, esta bitácora y la carátula.
- **Problemas resueltos:**
  - La computadora de Dariem no tenía Python, solo el acceso directo de la Microsoft Store. Se instaló Python 3.12.10 con winget.
  - Al diseñar los nodos vimos que, si un nodo recibe y envía en el mismo hilo, dos nodos pueden quedarse esperando el acuse del otro. Se separó: el hilo que recibe responde el acuse de inmediato y los envíos siguientes los hace otro hilo.
  - La carpeta `src/grpc` tiene el mismo nombre que la librería `grpc`. Para que Python no las confunda, los nodos se ejecutan con `python -m` desde la raíz del repositorio.

## Jueves 19 de noviembre de 2026

- **Presentes:** Dariem Benites, Erwin Bueno y Elian Mendoza.
- **Hipótesis, escrita antes de medir:**
  - **Mensajes de 100 caracteres:** sockets tendrá menor latencia que gRPC y enviará más mensajes por segundo. En sockets cada envío es el JSON con 4 bytes de longitud sobre una conexión TCP que ya está abierta. En gRPC cada llamada también pasa por HTTP/2, por la codificación con Protocol Buffers y por el pool de hilos del servidor. Con un mensaje corto, ese trabajo fijo de cada llamada es casi todo el tiempo.
  - **Mensajes de 10 000 caracteres:** las dos latencias subirán, porque hay más bytes que copiar y enviar. La diferencia relativa entre los dos mecanismos se achicará: con un mensaje grande pesa más el envío de los datos que el trabajo fijo de la llamada, y los dos formatos ocupan casi lo mismo, porque el texto pesa mucho más que las etiquetas del JSON o de Protocol Buffers.
  - **Tres clientes a la vez (A → B, B → C y C → B):** la latencia de cada cliente subirá, porque los procesos compiten por la CPU y porque nodo-B recibe de A y de C al mismo tiempo. El total de mensajes por segundo de los tres será mayor que con un solo cliente, pero no el triple, porque nodo-B se vuelve el cuello de botella.
- **Qué hicimos:**
  - Se acordó la hipótesis entre los tres antes de correr el experimento oficial.

## Jueves 19 de noviembre de 2026 (noche)

- **Presentes:** Elian Mendoza.
- **Qué hicimos:**
  - Se instaló Python 3.12.10 con el nuevo Python install manager (`py install 3.12`) y las librerías de `requirements.txt`.
  - Se generó el código de gRPC (`mensajeria_pb2.py` y `mensajeria_pb2_grpc.py`) a partir de `proto/mensajeria.proto` con `grpc_tools.protoc`.
  - Se subió el archivo `.proto` con el servicio `Mensajeria`, el mensaje `Mensaje` (mismos campos que el JSON de sockets) y el `Acuse`.
  - Se subieron `src/grpc/__init__.py` y `generar_codigo.bat`.
- **Problemas resueltos:**
  - El instalador nuevo de Python avisó que seguía instalado el "Python Launcher" antiguo, y por eso `py install` no funcionaba. Se desinstaló el Python Launcher desde Aplicaciones instaladas y el comando nuevo `py` empezó a funcionar.
  - El instalador puso Python 3.15 por defecto. Para usar la misma versión que el equipo se instaló la 3.12 y los comandos se ejecutan con `py -3.12`.
  - `pip install` se cortó con `Read timed out` por internet lento. Se repitió con `--default-timeout=120 --retries 10` y terminó bien.

## Viernes 20 de noviembre de 2026

- **Presentes:** Elian Mendoza.
- **Qué hicimos:**
  - Se subió `nodo.py` con los archivos generados `mensajeria_pb2.py` y `mensajeria_pb2_grpc.py`.
  - Se subió `medir_latencia.py`.
  - Se probaron en la computadora de Elian los tres nodos con gRPC (20 intercambios, 40 eventos) y la medición de latencia, y se tomaron las capturas 03 y 04.
- **Problemas resueltos:**
  - Al ejecutar los nodos salió `No module named 'src'`, porque la consola estaba en la carpeta externa del ZIP. Se entró a la carpeta interna con `cd AD-PE-U1-BBM-main` y los nodos corrieron bien.

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

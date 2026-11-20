"""Registro de eventos de Lamport y de latencias en CSV, más el encabezado que aparece en las capturas."""

import csv
import getpass
import os
import platform
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

CAMPOS_EVENTOS = ["mecanismo", "nodo", "evento", "reloj", "hora_real",
                  "origen", "destino", "reloj_mensaje", "mensaje"]

CAMPOS_LATENCIA = ["mecanismo", "tamano", "caracteres", "concurrente", "emisor", "receptor",
                   "corrida", "calentamiento", "envio", "rtt_ms", "hora_real"]

CAMPOS_CORRIDAS = ["mecanismo", "tamano", "caracteres", "concurrente", "emisor", "receptor",
                   "corrida", "calentamiento", "envios", "duracion_s", "mensajes_por_s"]


def ahora():
    return datetime.now().isoformat(timespec="microseconds")


def preparar_consola():
    """Evita que un carácter raro tumbe el programa al imprimir en cmd.exe."""
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(errors="replace")
        except AttributeError:
            pass


def encabezado(titulo):
    """Línea con usuario, máquina y hora para que las capturas muestren datos propios."""
    print(f"{titulo} | usuario: {getpass.getuser()} | equipo: {platform.node()} | "
          f"{datetime.now():%Y-%m-%d %H:%M:%S}", flush=True)


class RegistroEventos:
    """Guarda en memoria los eventos de un nodo y los escribe a su CSV al terminar."""

    def __init__(self, ruta, mecanismo):
        self.ruta = Path(ruta)
        self.mecanismo = mecanismo
        self._filas = []
        self._candado = threading.Lock()

    def anotar(self, nodo, evento, reloj, origen, destino, reloj_mensaje, mensaje):
        fila = {
            "mecanismo": self.mecanismo, "nodo": nodo, "evento": evento, "reloj": reloj,
            "hora_real": ahora(), "origen": origen, "destino": destino,
            "reloj_mensaje": reloj_mensaje, "mensaje": mensaje,
        }
        with self._candado:
            self._filas.append(fila)

    def guardar(self):
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        with self._candado:
            filas = sorted(self._filas, key=lambda f: f["reloj"])
        with open(self.ruta, "w", newline="", encoding="utf-8") as archivo:
            escritor = csv.DictWriter(archivo, fieldnames=CAMPOS_EVENTOS)
            escritor.writeheader()
            escritor.writerows(filas)
        return len(filas)


def _tomar_turno(ruta_turno, espera_max_s=60):
    """Crea el archivo de turno en exclusiva; si ya existe, otro proceso está escribiendo y se espera."""
    inicio = time.monotonic()
    while True:
        try:
            return os.open(ruta_turno, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if time.monotonic() - inicio > espera_max_s:
                raise TimeoutError(f"{ruta_turno} sigue ocupado después de {espera_max_s} s")
            time.sleep(0.01)


def agregar_filas(ruta, campos, filas):
    """Agrega filas a un CSV; escribe el encabezado solo si el archivo es nuevo.

    En la prueba de concurrencia tres procesos escriben el mismo CSV al terminar. Si escriben a la
    vez, las filas se pisan y se pierden, así que cada proceso espera su turno con un archivo .turno.
    """
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    turno = ruta.with_name(ruta.name + ".turno")
    descriptor = _tomar_turno(turno)
    try:
        nuevo = not ruta.exists()
        with open(ruta, "a", newline="", encoding="utf-8") as archivo:
            escritor = csv.DictWriter(archivo, fieldnames=campos)
            if nuevo:
                escritor.writeheader()
            escritor.writerows(filas)
    finally:
        os.close(descriptor)
        os.remove(turno)

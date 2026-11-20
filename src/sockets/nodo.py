"""Nodo del sistema con sockets TCP: un servidor que recibe JSON y un cliente con reloj de Lamport.

Uso (desde la raíz del repositorio, una consola por nodo):
    python -m src.sockets.nodo A
    python -m src.sockets.nodo B
    python -m src.sockets.nodo C
Con --modo receptor el nodo solo responde acuses; lo usa la medición de latencia.
"""

import argparse
import queue
import socket
import sys
import threading
import time
from pathlib import Path

from src.comun import config, escenario
from src.comun.lamport import RelojLamport
from src.comun.registro import RegistroEventos, encabezado, preparar_consola
from src.sockets.protocolo import enviar_json, recibir_json, sin_demora

MECANISMO = "sockets"


class NodoSocket:
    def __init__(self, letra, modo="escenario", carpeta=None):
        self.letra = letra
        self.nombre = config.NODOS[letra]["nombre"]
        self.puerto = config.NODOS[letra]["puerto"]
        self.modo = modo
        self.reloj = RelojLamport()
        carpeta = Path(carpeta) if carpeta else config.DATA
        self.registro = (RegistroEventos(carpeta / f"eventos_{MECANISMO}_{self.nombre}.csv", MECANISMO)
                         if modo == "escenario" else None)
        self.pendientes = queue.Queue()
        self.conexiones = {}
        self.candados = {otro: threading.Lock() for otro in config.NODOS if otro != letra}
        self.contador = threading.Lock()
        self.enviados = 0
        self.recibidos = 0
        self.esperados = escenario.conteo(letra) if modo == "escenario" else (0, 0)
        self.listo = threading.Event()
        self.servidor = None

    def iniciar_servidor(self):
        self.servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.servidor.bind((config.HOST, self.puerto))
        self.servidor.listen()
        threading.Thread(target=self._aceptar, daemon=True).start()
        print(f"[{self.nombre}] escuchando en {config.HOST}:{self.puerto} "
              f"({config.NODOS[self.letra]['rol']})", flush=True)

    def _aceptar(self):
        while True:
            try:
                conexion, _ = self.servidor.accept()
            except OSError:
                return
            sin_demora(conexion)
            threading.Thread(target=self._atender, args=(conexion,), daemon=True).start()

    def _atender(self, conexion):
        """Un hilo por conexión: lee mensajes, actualiza el reloj y responde el acuse."""
        with conexion:
            while True:
                try:
                    mensaje = recibir_json(conexion)
                except OSError:
                    return
                if mensaje is None:
                    return
                reloj = self.reloj.al_recibir(mensaje["timestamp"])
                if self.modo == "escenario":
                    self._procesar_recepcion(mensaje, reloj)
                enviar_json(conexion, {"sender": self.nombre, "timestamp": reloj, "message": "ack"})

    def _procesar_recepcion(self, mensaje, reloj):
        self.registro.anotar(self.nombre, "recepcion", reloj, mensaje["sender"], self.nombre,
                             mensaje["timestamp"], mensaje["message"])
        print(f"[{self.nombre}] recibe de {mensaje['sender']} | reloj {reloj} "
              f"(llegó con {mensaje['timestamp']}) | {mensaje['message']}", flush=True)
        origen = config.letra_de(mensaje["sender"])
        for paso in escenario.siguientes(self.letra, origen, mensaje["message"]):
            self.pendientes.put(paso)
        with self.contador:
            self.recibidos += 1
        self._revisar_fin()

    def _conexion(self, destino):
        """Abre (una sola vez) la conexión persistente hacia otro nodo, esperando a que esté arriba."""
        if destino in self.conexiones:
            return self.conexiones[destino]
        puerto = config.NODOS[destino]["puerto"]
        limite = time.time() + config.ESPERA_PARES_S
        while True:
            try:
                conexion = socket.create_connection((config.HOST, puerto), timeout=5)
                break
            except OSError:
                if time.time() > limite:
                    raise
                time.sleep(0.2)
        conexion.settimeout(None)
        sin_demora(conexion)
        self.conexiones[destino] = conexion
        return conexion

    def enviar(self, destino, texto):
        nombre_destino = config.NODOS[destino]["nombre"]
        with self.candados[destino]:
            conexion = self._conexion(destino)
            reloj = self.reloj.antes_de_enviar()
            if self.registro:
                self.registro.anotar(self.nombre, "envio", reloj, self.nombre, nombre_destino, reloj, texto)
            print(f"[{self.nombre}] envía a {nombre_destino} | reloj {reloj} | {texto}", flush=True)
            enviar_json(conexion, {"sender": self.nombre, "timestamp": reloj, "message": texto})
            acuse = recibir_json(conexion)
        if acuse is None:
            raise ConnectionError(f"{nombre_destino} cerró la conexión sin responder")
        return acuse

    def _despachar(self):
        """Hilo que envía los pasos pendientes, para no bloquear al hilo que recibe."""
        while True:
            _, destino, texto = self.pendientes.get()
            self.enviar(destino, texto)
            with self.contador:
                self.enviados += 1
            self._revisar_fin()

    def _revisar_fin(self):
        with self.contador:
            if (self.enviados, self.recibidos) == self.esperados:
                self.listo.set()

    def esperar_pares(self):
        for otro in config.NODOS:
            if otro != self.letra:
                self._conexion(otro)

    def cerrar(self):
        for conexion in self.conexiones.values():
            conexion.close()
        if self.servidor:
            self.servidor.close()


def ejecutar_escenario(nodo):
    nodo.iniciar_servidor()
    nodo.esperar_pares()
    print(f"[{nodo.nombre}] los tres nodos están en marcha: empiezan los 20 intercambios", flush=True)
    threading.Thread(target=nodo._despachar, daemon=True).start()
    for paso in escenario.iniciales(nodo.letra):
        nodo.pendientes.put(paso)
    if not nodo.listo.wait(config.ESPERA_FIN_S):
        print(f"[{nodo.nombre}] tiempo agotado: {nodo.enviados} envíos y {nodo.recibidos} recepciones", flush=True)
        return 1
    time.sleep(1.0)
    total = nodo.registro.guardar()
    print(f"[{nodo.nombre}] terminado: {nodo.enviados} envíos, {nodo.recibidos} recepciones, "
          f"{total} eventos en {nodo.registro.ruta.name}", flush=True)
    nodo.cerrar()
    return 0


def ejecutar_receptor(nodo):
    nodo.iniciar_servidor()
    print(f"[{nodo.nombre}] modo receptor: responde acuses para medir latencia (Ctrl+C para salir)", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        nodo.cerrar()
    return 0


def main():
    preparar_consola()
    parser = argparse.ArgumentParser(description="Nodo con sockets TCP y reloj de Lamport")
    parser.add_argument("nodo", choices=sorted(config.NODOS))
    parser.add_argument("--modo", choices=["escenario", "receptor"], default="escenario")
    parser.add_argument("--salida", default=str(config.DATA), help="carpeta de los CSV")
    args = parser.parse_args()
    encabezado(f"Sockets TCP | {config.NODOS[args.nodo]['nombre']}")
    nodo = NodoSocket(args.nodo, args.modo, args.salida)
    if args.modo == "escenario":
        return ejecutar_escenario(nodo)
    return ejecutar_receptor(nodo)


if __name__ == "__main__":
    sys.exit(main())

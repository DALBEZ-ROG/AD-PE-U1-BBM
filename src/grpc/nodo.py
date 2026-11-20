"""Nodo del sistema con gRPC: expone EnviarMensaje y llama al de los otros nodos con reloj de Lamport.

Uso (desde la raíz del repositorio, una consola por nodo):
    python -m src.grpc.nodo A
    python -m src.grpc.nodo B
    python -m src.grpc.nodo C
Con --modo receptor el nodo solo responde acuses; lo usa la medición de latencia.
"""

import argparse
import queue
import sys
import threading
import time
from concurrent import futures
from pathlib import Path

import grpc

from src.comun import config, escenario
from src.comun.lamport import RelojLamport
from src.comun.registro import RegistroEventos, encabezado, preparar_consola

# Código generado por grpcio-tools; src/grpc/__init__.py ya agregó esta carpeta a la ruta de búsqueda.
import mensajeria_pb2
import mensajeria_pb2_grpc

MECANISMO = "grpc"
# Sin proxy HTTP para 127.0.0.1 y reintentos de conexión cortos mientras arrancan los otros nodos.
OPCIONES_CANAL = [("grpc.enable_http_proxy", 0), ("grpc.max_reconnect_backoff_ms", 1000)]


class ServicioMensajeria(mensajeria_pb2_grpc.MensajeriaServicer):
    def __init__(self, nodo):
        self.nodo = nodo

    def EnviarMensaje(self, request, context):
        reloj = self.nodo.reloj.al_recibir(request.timestamp)
        if self.nodo.modo == "escenario":
            self.nodo.procesar_recepcion(request, reloj)
        return mensajeria_pb2.Acuse(receptor=self.nodo.nombre, timestamp=reloj, recibido=True)


class NodoGrpc:
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
        self.stubs = {}
        self.canales = {}
        self.contador = threading.Lock()
        self.enviados = 0
        self.recibidos = 0
        self.esperados = escenario.conteo(letra) if modo == "escenario" else (0, 0)
        self.listo = threading.Event()
        self.servidor = None

    def iniciar_servidor(self):
        self.servidor = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        mensajeria_pb2_grpc.add_MensajeriaServicer_to_server(ServicioMensajeria(self), self.servidor)
        self.servidor.add_insecure_port(f"{config.HOST}:{self.puerto}")
        self.servidor.start()
        print(f"[{self.nombre}] servidor gRPC en {config.HOST}:{self.puerto} "
              f"({config.NODOS[self.letra]['rol']})", flush=True)

    def procesar_recepcion(self, request, reloj):
        self.registro.anotar(self.nombre, "recepcion", reloj, request.sender, self.nombre,
                             request.timestamp, request.message)
        print(f"[{self.nombre}] recibe de {request.sender} | reloj {reloj} "
              f"(llegó con {request.timestamp}) | {request.message}", flush=True)
        origen = config.letra_de(request.sender)
        for paso in escenario.siguientes(self.letra, origen, request.message):
            self.pendientes.put(paso)
        with self.contador:
            self.recibidos += 1
        self._revisar_fin()

    def _stub(self, destino):
        """Crea (una sola vez) el canal y el stub hacia otro nodo, esperando a que esté listo."""
        if destino not in self.stubs:
            canal = grpc.insecure_channel(f"{config.HOST}:{config.NODOS[destino]['puerto']}",
                                          options=OPCIONES_CANAL)
            grpc.channel_ready_future(canal).result(timeout=config.ESPERA_PARES_S)
            self.canales[destino] = canal
            self.stubs[destino] = mensajeria_pb2_grpc.MensajeriaStub(canal)
        return self.stubs[destino]

    def enviar(self, destino, texto):
        nombre_destino = config.NODOS[destino]["nombre"]
        stub = self._stub(destino)
        reloj = self.reloj.antes_de_enviar()
        if self.registro:
            self.registro.anotar(self.nombre, "envio", reloj, self.nombre, nombre_destino, reloj, texto)
        print(f"[{self.nombre}] envía a {nombre_destino} | reloj {reloj} | {texto}", flush=True)
        return stub.EnviarMensaje(mensajeria_pb2.Mensaje(sender=self.nombre, timestamp=reloj, message=texto),
                                  timeout=10)

    def _despachar(self):
        """Hilo que hace las llamadas pendientes, para no bloquear a los hilos del servidor."""
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
                self._stub(otro)

    def cerrar(self):
        for canal in self.canales.values():
            canal.close()
        if self.servidor:
            self.servidor.stop(grace=1)


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
    parser = argparse.ArgumentParser(description="Nodo con gRPC y reloj de Lamport")
    parser.add_argument("nodo", choices=sorted(config.NODOS))
    parser.add_argument("--modo", choices=["escenario", "receptor"], default="escenario")
    parser.add_argument("--salida", default=str(config.DATA), help="carpeta de los CSV")
    args = parser.parse_args()
    encabezado(f"gRPC | {config.NODOS[args.nodo]['nombre']}")
    nodo = NodoGrpc(args.nodo, args.modo, args.salida)
    if args.modo == "escenario":
        return ejecutar_escenario(nodo)
    return ejecutar_receptor(nodo)


if __name__ == "__main__":
    sys.exit(main())

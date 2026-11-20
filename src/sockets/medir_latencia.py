"""Mide la latencia de ida y vuelta con sockets TCP contra un nodo en modo receptor.

Ejemplo: con `python -m src.sockets.nodo B --modo receptor` corriendo en otra consola,
    python -m src.sockets.medir_latencia --emisor A --receptor B
hace 1 corrida de calentamiento y 5 corridas de 100 envíos con mensajes de 100 y 10 000 caracteres.
"""

import argparse
import socket
import sys
import time

from src.comun import config
from src.comun.lamport import RelojLamport
from src.comun.medicion import esperar_hasta, medir
from src.comun.registro import encabezado, preparar_consola
from src.sockets.protocolo import enviar_json, recibir_json, sin_demora


def conectar(destino):
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
    return conexion


def main():
    preparar_consola()
    parser = argparse.ArgumentParser(description="Latencia de ida y vuelta con sockets TCP")
    parser.add_argument("--emisor", choices=sorted(config.NODOS), default="A")
    parser.add_argument("--receptor", choices=sorted(config.NODOS), default="B")
    parser.add_argument("--tamanos", nargs="+", choices=list(config.TAMANOS), default=list(config.TAMANOS))
    parser.add_argument("--envios", type=int, default=config.ENVIOS_POR_CORRIDA)
    parser.add_argument("--corridas", type=int, default=config.CORRIDAS)
    parser.add_argument("--calentamiento", type=int, default=config.CALENTAMIENTO)
    parser.add_argument("--concurrente", action="store_true", help="marca la prueba con los tres clientes a la vez")
    parser.add_argument("--iniciar-en", type=float, default=None, help="instante (epoch) en que arrancar")
    parser.add_argument("--salida", default=str(config.DATA))
    args = parser.parse_args()

    emisor = config.NODOS[args.emisor]["nombre"]
    receptor = config.NODOS[args.receptor]["nombre"]
    encabezado(f"Latencia con sockets TCP | {emisor} -> {receptor}")
    conexion = conectar(args.receptor)
    reloj = RelojLamport()

    def enviar(marca, texto):
        enviar_json(conexion, {"sender": emisor, "timestamp": marca, "message": texto})
        if recibir_json(conexion) is None:
            raise ConnectionError(f"{receptor} cerró la conexión")

    esperar_hasta(args.iniciar_en)
    for tamano in args.tamanos:
        medir(enviar, "sockets", emisor, receptor, tamano, reloj, args.envios, args.corridas,
              args.calentamiento, args.concurrente, args.salida)
    conexion.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

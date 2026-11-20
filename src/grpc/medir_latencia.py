"""Mide la latencia de ida y vuelta con gRPC contra un nodo en modo receptor.

Ejemplo: con `python -m src.grpc.nodo B --modo receptor` corriendo en otra consola,
    python -m src.grpc.medir_latencia --emisor A --receptor B
hace 1 corrida de calentamiento y 5 corridas de 100 llamadas con mensajes de 100 y 10 000 caracteres.
"""

import argparse
import sys

import grpc

from src.comun import config
from src.comun.lamport import RelojLamport
from src.comun.medicion import esperar_hasta, medir
from src.comun.registro import encabezado, preparar_consola

# Código generado por grpcio-tools; src/grpc/__init__.py ya agregó esta carpeta a la ruta de búsqueda.
import mensajeria_pb2
import mensajeria_pb2_grpc

OPCIONES_CANAL = [("grpc.enable_http_proxy", 0), ("grpc.max_reconnect_backoff_ms", 1000)]


def main():
    preparar_consola()
    parser = argparse.ArgumentParser(description="Latencia de ida y vuelta con gRPC")
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
    encabezado(f"Latencia con gRPC | {emisor} -> {receptor}")
    canal = grpc.insecure_channel(f"{config.HOST}:{config.NODOS[args.receptor]['puerto']}",
                                  options=OPCIONES_CANAL)
    grpc.channel_ready_future(canal).result(timeout=config.ESPERA_PARES_S)
    stub = mensajeria_pb2_grpc.MensajeriaStub(canal)
    reloj = RelojLamport()

    def enviar(marca, texto):
        # Sin plazo (timeout) para medir igual que en sockets, donde el cliente también espera sin límite.
        stub.EnviarMensaje(mensajeria_pb2.Mensaje(sender=emisor, timestamp=marca, message=texto))

    esperar_hasta(args.iniciar_en)
    for tamano in args.tamanos:
        medir(enviar, "grpc", emisor, receptor, tamano, reloj, args.envios, args.corridas,
              args.calentamiento, args.concurrente, args.salida)
    canal.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

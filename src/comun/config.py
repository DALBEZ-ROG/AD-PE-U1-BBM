"""Configuración compartida por los tres nodos (sockets y gRPC usan los mismos puertos, no al mismo tiempo)."""

from pathlib import Path

HOST = "127.0.0.1"

NODOS = {
    "A": {"nombre": "nodo-A", "puerto": 5000, "rol": "cliente de reservas"},
    "B": {"nombre": "nodo-B", "puerto": 5001, "rol": "servidor de aplicación"},
    "C": {"nombre": "nodo-C", "puerto": 5002, "rol": "servicio de pagos"},
}

RAIZ = Path(__file__).resolve().parents[2]
DATA = RAIZ / "data"

TAMANOS = {"corto": 100, "largo": 10_000}
ENVIOS_POR_CORRIDA = 100
CORRIDAS = 5
CALENTAMIENTO = 1

ESPERA_PARES_S = 30
ESPERA_FIN_S = 120


def letra_de(nombre):
    """Devuelve la letra del nodo a partir de su nombre (nodo-B -> B)."""
    for letra, datos in NODOS.items():
        if datos["nombre"] == nombre:
            return letra
    raise ValueError(f"Nodo desconocido: {nombre}")


def contenido_de_tamano(caracteres):
    """Texto de relleno con la longitud exacta pedida para medir latencia."""
    base = "abcdefghijklmnopqrstuvwxyz0123456789"
    repeticiones = caracteres // len(base) + 1
    return (base * repeticiones)[:caracteres]

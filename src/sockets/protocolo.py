"""Formato de los mensajes sobre TCP: 4 bytes con la longitud y después el JSON en UTF-8.

TCP entrega un flujo de bytes sin cortes entre mensajes, así que el que lee necesita saber
dónde termina cada uno. Por eso cada JSON va precedido de su tamaño.
"""

import json
import socket
import struct

CABECERA = struct.Struct(">I")


def enviar_json(conexion, datos):
    cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
    conexion.sendall(CABECERA.pack(len(cuerpo)) + cuerpo)


def _recibir_exacto(conexion, cantidad):
    partes = bytearray()
    while len(partes) < cantidad:
        bloque = conexion.recv(cantidad - len(partes))
        if not bloque:
            return None
        partes.extend(bloque)
    return bytes(partes)


def recibir_json(conexion):
    """Devuelve el siguiente mensaje como diccionario, o None si el otro lado cerró."""
    cabecera = _recibir_exacto(conexion, CABECERA.size)
    if cabecera is None:
        return None
    (longitud,) = CABECERA.unpack(cabecera)
    cuerpo = _recibir_exacto(conexion, longitud)
    if cuerpo is None:
        return None
    return json.loads(cuerpo.decode("utf-8"))


def sin_demora(conexion):
    """Desactiva el algoritmo de Nagle para no sumar espera artificial a mensajes cortos."""
    conexion.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

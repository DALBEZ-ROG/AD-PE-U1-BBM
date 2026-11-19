"""Reloj lógico de Lamport, seguro para usarlo desde varios hilos del mismo nodo."""

import threading


class RelojLamport:
    def __init__(self):
        self._valor = 0
        self._candado = threading.Lock()

    @property
    def valor(self):
        with self._candado:
            return self._valor

    def antes_de_enviar(self):
        """Regla de envío: el reloj sube en 1 y ese valor viaja en el mensaje."""
        with self._candado:
            self._valor += 1
            return self._valor

    def al_recibir(self, recibido):
        """Regla de recepción: max(local, recibido) + 1."""
        with self._candado:
            self._valor = max(self._valor, int(recibido)) + 1
            return self._valor

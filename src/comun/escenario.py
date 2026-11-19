"""Los 20 intercambios del sistema de reservas de vuelos (diseño de FORM-TL-01).

nodo-A es el cliente de reservas, nodo-B el servidor de aplicación y nodo-C el servicio de pagos.
Cada paso se envía cuando su nodo recibe el paso del que depende; los pasos 1 y 2 no dependen
de nada y salen a la vez desde A y C, así que son eventos concurrentes.
"""

PASOS = [
    (1, "A", "B", "Consultar vuelos UIO-GYE para el 15/12", None),
    (2, "C", "B", "Servicio de pagos disponible", None),
    (3, "B", "A", "Hay 3 vuelos: 07:00, 12:30 y 18:45", 1),
    (4, "A", "B", "Reservar asiento 12A en el vuelo de las 07:00", 3),
    (5, "B", "C", "Cobrar 85,50 USD con el token tok_4821", 4),
    (6, "C", "B", "Pago aprobado: transacción TX-1001", 5),
    (7, "B", "A", "Reserva confirmada: código RSV-7F3K", 6),
    (8, "A", "B", "Consultar el estado de RSV-7F3K", 7),
    (9, "B", "A", "RSV-7F3K está CONFIRMADA", 8),
    (10, "A", "B", "Agregar una maleta de 23 kg a RSV-7F3K", 9),
    (11, "B", "C", "Cobrar 30,00 USD de equipaje con tok_4821", 10),
    (12, "C", "B", "Pago rechazado: fondos insuficientes", 11),
    (13, "B", "A", "No se pudo cobrar el equipaje", 12),
    (14, "A", "B", "Reintentar el cobro con la tarjeta tok_9930", 13),
    (15, "B", "C", "Cobrar 30,00 USD de equipaje con tok_9930", 14),
    (16, "C", "B", "Pago aprobado: transacción TX-1002", 15),
    (17, "B", "A", "Equipaje agregado a RSV-7F3K", 16),
    (18, "A", "B", "Solicitar los comprobantes de pago", 17),
    (19, "B", "C", "Generar comprobantes de TX-1001 y TX-1002", 18),
    (20, "C", "B", "Comprobantes generados y enviados al correo", 19),
]

_POR_TEXTO = {(origen, texto): numero for numero, origen, _, texto, _ in PASOS}


def iniciales(letra):
    """Pasos que el nodo envía apenas arranca."""
    return [(numero, destino, texto) for numero, origen, destino, texto, previo in PASOS
            if origen == letra and previo is None]


def siguientes(letra, origen, texto):
    """Pasos que el nodo debe enviar después de recibir `texto` desde `origen`."""
    numero = _POR_TEXTO.get((origen, texto))
    if numero is None:
        return []
    return [(n, destino, t) for n, o, destino, t, previo in PASOS if o == letra and previo == numero]


def conteo(letra):
    """Cuántos mensajes envía y recibe el nodo en el escenario completo."""
    envios = sum(1 for _, origen, _, _, _ in PASOS if origen == letra)
    recepciones = sum(1 for _, _, destino, _, _ in PASOS if destino == letra)
    return envios, recepciones

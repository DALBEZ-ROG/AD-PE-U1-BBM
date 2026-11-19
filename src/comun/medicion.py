"""Protocolo de medición común a sockets y gRPC, para que los dos se midan igual.

Cada corrida manda N mensajes seguidos y mide con time.perf_counter() la ida y vuelta de cada uno
(desde que se envía hasta que llega el acuse). La corrida 0 es de calentamiento y se marca para
descartarla en el análisis, pero también se guarda: los datos crudos van completos.
"""

import time
from pathlib import Path

from src.comun import config
from src.comun.registro import (CAMPOS_CORRIDAS, CAMPOS_LATENCIA, agregar_filas, ahora)


def esperar_hasta(instante):
    """Duerme hasta un instante de reloj de pared (sirve para arrancar varios clientes a la vez)."""
    if instante:
        restante = instante - time.time()
        if restante > 0:
            time.sleep(restante)


def medir(enviar, mecanismo, emisor, receptor, tamano, reloj, envios=None, corridas=None,
          calentamiento=None, concurrente=False, carpeta=None):
    """Ejecuta las corridas y escribe latencia_<mecanismo>.csv y corridas_<mecanismo>.csv.

    `enviar(timestamp, texto)` es la función propia de cada mecanismo: manda el mensaje y
    devuelve cuando llega el acuse.
    """
    envios = envios or config.ENVIOS_POR_CORRIDA
    corridas = config.CORRIDAS if corridas is None else corridas
    calentamiento = config.CALENTAMIENTO if calentamiento is None else calentamiento
    carpeta = Path(carpeta) if carpeta else config.DATA
    caracteres = config.TAMANOS[tamano]
    texto = config.contenido_de_tamano(caracteres)

    filas_latencia, filas_corridas = [], []
    for corrida in range(calentamiento + corridas):
        es_calentamiento = corrida < calentamiento
        numero = 0 if es_calentamiento else corrida - calentamiento + 1
        inicio_corrida = time.perf_counter()
        for envio in range(1, envios + 1):
            marca = reloj.antes_de_enviar()
            t0 = time.perf_counter()
            enviar(marca, texto)
            t1 = time.perf_counter()
            filas_latencia.append({
                "mecanismo": mecanismo, "tamano": tamano, "caracteres": caracteres,
                "concurrente": int(concurrente), "emisor": emisor, "receptor": receptor,
                "corrida": numero, "calentamiento": int(es_calentamiento), "envio": envio,
                "rtt_ms": round((t1 - t0) * 1000, 6), "hora_real": ahora(),
            })
        duracion = time.perf_counter() - inicio_corrida
        filas_corridas.append({
            "mecanismo": mecanismo, "tamano": tamano, "caracteres": caracteres,
            "concurrente": int(concurrente), "emisor": emisor, "receptor": receptor,
            "corrida": numero, "calentamiento": int(es_calentamiento), "envios": envios,
            "duracion_s": round(duracion, 6), "mensajes_por_s": round(envios / duracion, 3),
        })
        etiqueta = "calentamiento" if es_calentamiento else f"corrida {numero}"
        promedio = sum(f["rtt_ms"] for f in filas_latencia[-envios:]) / envios
        print(f"[{emisor} -> {receptor}] {mecanismo} {tamano} {etiqueta}: "
              f"{envios} envíos, promedio {promedio:.3f} ms, {envios / duracion:.1f} mensajes/s", flush=True)

    agregar_filas(carpeta / f"latencia_{mecanismo}.csv", CAMPOS_LATENCIA, filas_latencia)
    agregar_filas(carpeta / f"corridas_{mecanismo}.csv", CAMPOS_CORRIDAS, filas_corridas)
    return filas_latencia, filas_corridas

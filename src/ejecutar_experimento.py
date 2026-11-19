"""Ejecuta el protocolo experimental completo en esta máquina y deja los datos crudos en data/.

Uso, desde la raíz del repositorio y con las demás aplicaciones cerradas:
    python -m src.ejecutar_experimento --notas "solo cmd abierto"

Para cada mecanismo (primero sockets y después gRPC) hace tres pruebas, cada una con procesos nuevos:
  1. escenario: los tres nodos hacen los 20 intercambios -> eventos_<mecanismo>_nodo-X.csv
  2. latencia: nodo-A envía a nodo-B; por cada tamaño de mensaje hay 1 corrida de calentamiento
     y 5 corridas de 100 envíos -> latencia_<mecanismo>.csv y corridas_<mecanismo>.csv
  3. concurrencia: A->B, B->C y C->B envían a la vez, con las mismas corridas (concurrente = 1)
Antes de empezar guarda las condiciones de la máquina en condiciones.json y al final escribe
SHA256SUMS con la huella de cada archivo. Lo que imprime cada proceso queda en data/logs/.
"""

import argparse
import ctypes
import getpass
import hashlib
import json
import os
import platform
import socket
import subprocess
import sys
import time
from datetime import datetime
from importlib import metadata
from pathlib import Path

from src.comun import config
from src.comun.registro import encabezado, preparar_consola

MECANISMOS = ("sockets", "grpc")
PAR_LATENCIA = ("A", "B")
PARES_CONCURRENTES = (("A", "B"), ("B", "C"), ("C", "B"))
LIBRERIAS = ("grpcio", "grpcio-tools", "protobuf", "pandas", "numpy", "matplotlib")
GENERADOS = ("eventos_*.csv", "latencia_*.csv", "corridas_*.csv", "condiciones.json", "SHA256SUMS", "logs/*.log")
ARRANQUE_S = 5
LIMITE_CLIENTE_S = 600


def nombre(letra):
    return config.NODOS[letra]["nombre"]


# ---------------------------------------------------------------- condiciones de la máquina

def sistema_operativo():
    if os.name == "nt":
        return f"Windows {platform.release()} {platform.win32_edition() or ''} (versión {platform.version()})"
    return platform.platform()


def nombre_procesador():
    if os.name == "nt":
        try:
            import winreg
            ruta = r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, ruta) as clave:
                return winreg.QueryValueEx(clave, "ProcessorNameString")[0].strip()
        except OSError:
            pass
    elif sys.platform.startswith("linux"):
        try:
            for linea in Path("/proc/cpuinfo").read_text().splitlines():
                if linea.startswith("model name"):
                    return linea.split(":", 1)[1].strip()
        except OSError:
            pass
    return platform.processor() or "desconocido"


def memoria_gb():
    """Memoria física total y disponible, en GB."""
    if os.name == "nt":
        class EstadoMemoria(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        estado = EstadoMemoria()
        estado.dwLength = ctypes.sizeof(EstadoMemoria)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(estado))
        return round(estado.ullTotalPhys / 1024 ** 3, 1), round(estado.ullAvailPhys / 1024 ** 3, 1)
    try:
        pagina = os.sysconf("SC_PAGE_SIZE")
        return (round(pagina * os.sysconf("SC_PHYS_PAGES") / 1024 ** 3, 1),
                round(pagina * os.sysconf("SC_AVPHYS_PAGES") / 1024 ** 3, 1))
    except (ValueError, OSError, AttributeError):
        return None, None


def plan_de_energia():
    if os.name != "nt":
        return None
    try:
        salida = subprocess.run(["powercfg", "/getactivescheme"], capture_output=True, text=True,
                                encoding="oem", errors="replace", timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    if "(" in salida:
        return salida[salida.rfind("(") + 1:salida.rfind(")")]
    return salida or None


def versiones():
    resultado = {}
    for libreria in LIBRERIAS:
        try:
            resultado[libreria] = metadata.version(libreria)
        except metadata.PackageNotFoundError:
            resultado[libreria] = "no instalada"
    return resultado


def bytes_por_mensaje():
    """Tamaño de un mensaje ya codificado: JSON con su cabecera de 4 bytes, y Protocol Buffers."""
    try:
        import src.grpc  # noqa: F401  agrega la carpeta del código generado a la ruta
        import mensajeria_pb2
    except ImportError:
        mensajeria_pb2 = None
    resultado = {}
    for tamano, caracteres in config.TAMANOS.items():
        texto = config.contenido_de_tamano(caracteres)
        cuerpo = json.dumps({"sender": "nodo-A", "timestamp": 1, "message": texto}, ensure_ascii=False)
        datos = {"caracteres": caracteres, "sockets_json_con_cabecera": len(cuerpo.encode("utf-8")) + 4}
        if mensajeria_pb2:
            mensaje = mensajeria_pb2.Mensaje(sender="nodo-A", timestamp=1, message=texto)
            datos["grpc_protobuf"] = mensaje.ByteSize()
        resultado[tamano] = datos
    return resultado


def condiciones(notas, envios, corridas, calentamiento, mecanismos):
    total, disponible = memoria_gb()
    return {
        "fecha_inicio": datetime.now().isoformat(timespec="seconds"),
        "usuario": getpass.getuser(),
        "equipo": platform.node(),
        "sistema_operativo": sistema_operativo(),
        "procesador": nombre_procesador(),
        "nucleos_logicos": os.cpu_count(),
        "memoria_total_gb": total,
        "memoria_disponible_al_inicio_gb": disponible,
        "plan_de_energia": plan_de_energia(),
        "python": f"{platform.python_implementation()} {platform.python_version()}",
        "librerias": versiones(),
        "despliegue": "procesos en la misma máquina (127.0.0.1, puertos 5000, 5001 y 5002), sin contenedores",
        "protocolo": {
            "mecanismos": list(mecanismos),
            "envios_por_corrida": envios,
            "corridas": corridas,
            "corridas_de_calentamiento": calentamiento,
            "tamanos_en_caracteres": config.TAMANOS,
            "latencia": f"{nombre(PAR_LATENCIA[0])} -> {nombre(PAR_LATENCIA[1])}",
            "concurrencia": [f"{nombre(e)} -> {nombre(r)}" for e, r in PARES_CONCURRENTES],
        },
        "bytes_por_mensaje": bytes_por_mensaje(),
        "notas": notas,
    }


# ---------------------------------------------------------------- procesos

def lanzar(carpeta, nombre_log, modulo, *argumentos):
    """Arranca un módulo del repositorio con este mismo Python; su salida va a data/logs/."""
    log = open(carpeta / "logs" / f"{nombre_log}.log", "w", encoding="utf-8")
    comando = [sys.executable, "-m", modulo, *argumentos, "--salida", str(carpeta)]
    entorno = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    proceso = subprocess.Popen(comando, cwd=config.RAIZ, stdout=log, stderr=subprocess.STDOUT, env=entorno)
    return proceso, log, carpeta / "logs" / f"{nombre_log}.log"


def mostrar(ruta, solo=None):
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        if solo is None or solo in linea:
            print(f"    {linea}")


def esperar(procesos, limite_s):
    """Espera a que terminen; si alguno falla, muestra el final de su log y detiene todo."""
    fallidos = []
    for proceso, log, ruta in procesos:
        try:
            codigo = proceso.wait(timeout=limite_s)
        except subprocess.TimeoutExpired:
            proceso.kill()
            codigo = "tiempo agotado"
        log.close()
        if codigo != 0:
            fallidos.append((ruta, codigo))
    for ruta, codigo in fallidos:
        print(f"  ERROR en {ruta.name} ({codigo}). Últimas líneas:")
        for linea in ruta.read_text(encoding="utf-8").splitlines()[-15:]:
            print(f"    {linea}")
    if fallidos:
        raise SystemExit(1)


def detener(procesos):
    """Cierra los nodos en modo receptor, que no terminan solos."""
    for proceso, log, _ in procesos:
        proceso.terminate()
        try:
            proceso.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proceso.kill()
        log.close()


def puertos_ocupados():
    ocupados = []
    for datos in config.NODOS.values():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as prueba:
            try:
                prueba.bind((config.HOST, datos["puerto"]))
            except OSError:
                ocupados.append(datos["puerto"])
    return ocupados


# ---------------------------------------------------------------- pruebas

def escenario(mecanismo, carpeta):
    print(f"\n[{mecanismo}] escenario de 20 intercambios entre los tres nodos")
    procesos = [lanzar(carpeta, f"{mecanismo}_escenario_{nombre(letra)}", f"src.{mecanismo}.nodo", letra)
                for letra in config.NODOS]
    esperar(procesos, config.ESPERA_PARES_S + config.ESPERA_FIN_S)
    for _, _, ruta in procesos:
        mostrar(ruta, solo="terminado")


def latencia(mecanismo, carpeta, opciones):
    emisor, receptor = PAR_LATENCIA
    print(f"\n[{mecanismo}] latencia de {nombre(emisor)} a {nombre(receptor)}")
    receptores = [lanzar(carpeta, f"{mecanismo}_latencia_receptor_{nombre(receptor)}",
                         f"src.{mecanismo}.nodo", receptor, "--modo", "receptor")]
    try:
        cliente = lanzar(carpeta, f"{mecanismo}_latencia_{nombre(emisor)}_a_{nombre(receptor)}",
                         f"src.{mecanismo}.medir_latencia", "--emisor", emisor, "--receptor", receptor, *opciones)
        esperar([cliente], LIMITE_CLIENTE_S)
        mostrar(cliente[2], solo=" -> ")
    finally:
        detener(receptores)


def concurrencia(mecanismo, carpeta, opciones):
    pares = ", ".join(f"{nombre(e)} -> {nombre(r)}" for e, r in PARES_CONCURRENTES)
    print(f"\n[{mecanismo}] concurrencia: {pares} a la vez")
    destinos = sorted({receptor for _, receptor in PARES_CONCURRENTES})
    receptores = [lanzar(carpeta, f"{mecanismo}_concurrente_receptor_{nombre(r)}",
                         f"src.{mecanismo}.nodo", r, "--modo", "receptor") for r in destinos]
    try:
        for tamano in config.TAMANOS:
            inicio = time.time() + ARRANQUE_S
            clientes = [lanzar(carpeta, f"{mecanismo}_concurrente_{tamano}_{nombre(e)}_a_{nombre(r)}",
                               f"src.{mecanismo}.medir_latencia", "--emisor", e, "--receptor", r,
                               "--tamanos", tamano, "--concurrente", "--iniciar-en", f"{inicio:.3f}", *opciones)
                        for e, r in PARES_CONCURRENTES]
            esperar(clientes, LIMITE_CLIENTE_S)
            for cliente in clientes:
                mostrar(cliente[2], solo=" -> ")
    finally:
        detener(receptores)


# ---------------------------------------------------------------- integridad de los datos

def escribir_sumas(carpeta):
    """SHA256SUMS en el formato de sha256sum, para comprobar después que nadie editó los datos."""
    archivos = sorted(p for p in carpeta.rglob("*") if p.is_file() and p.name != "SHA256SUMS")
    lineas = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(carpeta).as_posix()}"
              for p in archivos]
    (carpeta / "SHA256SUMS").write_text("\n".join(lineas) + "\n", encoding="utf-8", newline="\n")
    return len(lineas)


def escribir_json(ruta, datos):
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def main():
    preparar_consola()
    parser = argparse.ArgumentParser(description="Protocolo experimental completo de la PE-U1")
    parser.add_argument("--mecanismos", nargs="+", choices=MECANISMOS, default=list(MECANISMOS))
    parser.add_argument("--envios", type=int, default=config.ENVIOS_POR_CORRIDA)
    parser.add_argument("--corridas", type=int, default=config.CORRIDAS)
    parser.add_argument("--calentamiento", type=int, default=config.CALENTAMIENTO)
    parser.add_argument("--salida", default=str(config.DATA), help="carpeta de los datos (por defecto data/)")
    parser.add_argument("--notas", default="", help="lo que el script no puede ver: aplicaciones abiertas, etc.")
    parser.add_argument("--sobrescribir", action="store_true",
                        help="borra los datos de una ejecución anterior que estén en la carpeta de salida")
    args = parser.parse_args()

    carpeta = Path(args.salida).resolve()
    anteriores = sorted({p for patron in GENERADOS for p in carpeta.glob(patron)})
    if anteriores and not args.sobrescribir:
        print(f"Ya hay datos de una ejecución anterior en {carpeta} ({len(anteriores)} archivos).")
        print("Para repetir el experimento usa --sobrescribir, que los borra, o --salida con otra carpeta.")
        return 1
    ocupados = puertos_ocupados()
    if ocupados:
        print(f"Los puertos {ocupados} están ocupados: cierra los nodos que sigan abiertos y vuelve a intentar.")
        return 1
    for archivo in anteriores:
        archivo.unlink()
    (carpeta / "logs").mkdir(parents=True, exist_ok=True)

    encabezado("Experimento PE-U1")
    inicio = time.perf_counter()
    datos = condiciones(args.notas, args.envios, args.corridas, args.calentamiento, args.mecanismos)
    escribir_json(carpeta / "condiciones.json", datos)
    print(f"Máquina: {datos['sistema_operativo']}, {datos['procesador']}, {datos['nucleos_logicos']} núcleos "
          f"lógicos, {datos['memoria_total_gb']} GB de RAM, {datos['python']}")
    print(f"Protocolo: {args.calentamiento} corrida de calentamiento + {args.corridas} corridas de "
          f"{args.envios} envíos por tamaño ({', '.join(f'{c} caracteres' for c in config.TAMANOS.values())})")

    opciones = ["--envios", str(args.envios), "--corridas", str(args.corridas),
                "--calentamiento", str(args.calentamiento)]
    for mecanismo in args.mecanismos:
        escenario(mecanismo, carpeta)
        latencia(mecanismo, carpeta, opciones)
        concurrencia(mecanismo, carpeta, opciones)

    datos["fecha_fin"] = datetime.now().isoformat(timespec="seconds")
    datos["duracion_s"] = round(time.perf_counter() - inicio, 1)
    escribir_json(carpeta / "condiciones.json", datos)
    total = escribir_sumas(carpeta)
    print(f"\nListo en {datos['duracion_s']} s. SHA256SUMS tiene la huella de {total} archivos de {carpeta}.")
    print("Siguiente paso: python analysis\\analizar.py  y  python analysis\\verificar_lamport.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

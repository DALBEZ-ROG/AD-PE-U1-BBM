r"""Estadísticas, gráficos y tablas de la PE-U1 a partir de los CSV de data/.

Uso, desde la raíz del repositorio:   python analysis\analizar.py

1. Comprueba data/SHA256SUMS, para trabajar solo con datos sin modificar.
2. Para cada mecanismo, tamaño de mensaje y prueba (un cliente, o tres clientes a la vez) calcula la
   media, la mediana, la desviación estándar y el percentil 95 de la latencia, y el rendimiento en
   mensajes por segundo. La corrida de calentamiento (corrida 0) queda en los CSV pero no entra en
   los cálculos.
3. El intervalo de confianza del 95 % de la media sale de las medias de cada corrida, con la t de
   Student, porque las corridas son las repeticiones del experimento.
4. En la prueba de tres clientes a la vez también separa la latencia por cliente, para ver si el
   receptor que atiende a dos clientes (nodo-B) los hace esperar más.
Escribe en analysis/: resultados/*.csv, tablas/*.tex (para incluirlas en el informe con \input)
y figuras/*.pdf y *.png.
"""

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import to_rgba  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]

MECANISMOS = {"sockets": "Sockets TCP", "grpc": "gRPC"}
TAMANOS = {"corto": "100 caracteres", "largo": "10 000 caracteres"}
PRUEBAS = {0: "Un cliente", 1: "Tres clientes a la vez"}
SUBTITULOS = {0: "nodo-A → nodo-B", 1: "A → B, B → C y C → B"}

COLOR = {"sockets": "#2a78d6", "grpc": "#eb6834"}
TINTA, TINTA_2, TINTA_3 = "#0b0b0b", "#52514e", "#898781"
REJILLA, EJE = "#e1e0d9", "#c3c2b7"

# t de Student al 95 % (dos colas) según los grados de libertad; con más de 30 se usa 1,96.
T_975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262,
         10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110,
         18: 2.101, 19: 2.093, 20: 2.086, 21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
         26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042}


# ---------------------------------------------------------------- datos

def comprobar_sumas(datos):
    ruta = datos / "SHA256SUMS"
    if not ruta.exists():
        print("ATENCIÓN: no hay SHA256SUMS; no se puede comprobar que los datos estén sin modificar.")
        return False
    lineas = [linea for linea in ruta.read_text(encoding="utf-8").splitlines() if linea.strip()]
    distintos = []
    for linea in lineas:
        suma, nombre = linea.split(maxsplit=1)
        archivo = datos / nombre.lstrip("*")
        if not archivo.exists() or hashlib.sha256(archivo.read_bytes()).hexdigest() != suma:
            distintos.append(nombre)
    if distintos:
        print(f"ATENCIÓN: {len(distintos)} archivos no coinciden con SHA256SUMS: {', '.join(distintos)}")
        return False
    print(f"SHA256SUMS: los {len(lineas)} archivos de {datos.name}/ coinciden con su huella.")
    return True


def cargar(datos, patron):
    archivos = sorted(datos.glob(patron))
    if not archivos:
        sys.exit(f"No hay archivos {patron} en {datos}. Primero ejecuta: python -m src.ejecutar_experimento")
    return pd.concat([pd.read_csv(archivo) for archivo in archivos], ignore_index=True)


def media_e_intervalo(valores):
    """Media y semiancho del intervalo de confianza del 95 % (t de Student)."""
    valores = np.asarray(valores, dtype=float)
    k = len(valores)
    if k < 2:
        return (float(valores.mean()) if k else math.nan), math.nan
    t = T_975.get(k - 1, 1.96)
    return float(valores.mean()), float(t * valores.std(ddof=1) / math.sqrt(k))


def estadisticas(latencias, corridas):
    filas = []
    for mecanismo in MECANISMOS:
        for tamano in TAMANOS:
            for concurrente in PRUEBAS:
                def elegir(tabla):
                    return tabla[(tabla.mecanismo == mecanismo) & (tabla.tamano == tamano)
                                 & (tabla.concurrente == concurrente) & (tabla.calentamiento == 0)]
                lat, cor = elegir(latencias), elegir(corridas)
                if lat.empty:
                    continue
                rtt = lat.rtt_ms.to_numpy()
                _, ic_media = media_e_intervalo(lat.groupby(["emisor", "corrida"]).rtt_ms.mean())
                mps, ic_mps = media_e_intervalo(cor.mensajes_por_s)
                total, ic_total = media_e_intervalo(cor.groupby("corrida").mensajes_por_s.sum())
                filas.append({
                    "mecanismo": mecanismo, "tamano": tamano, "caracteres": int(lat.caracteres.iloc[0]),
                    "concurrente": concurrente, "clientes": lat.emisor.nunique(),
                    "corridas": cor.corrida.nunique(), "n": len(rtt),
                    "media_ms": rtt.mean(), "ic95_media_ms": ic_media, "mediana_ms": np.median(rtt),
                    "de_ms": rtt.std(ddof=1), "p95_ms": np.percentile(rtt, 95),
                    "min_ms": rtt.min(), "max_ms": rtt.max(),
                    "mensajes_por_s": mps, "ic95_mensajes_por_s": ic_mps,
                    "mensajes_por_s_total": total, "ic95_mensajes_por_s_total": ic_total,
                })
    return pd.DataFrame(filas)


def por_cliente(latencias, corridas):
    """Prueba de tres clientes a la vez, separada por cliente (emisor y receptor)."""
    lat = latencias[(latencias.concurrente == 1) & (latencias.calentamiento == 0)]
    cor = corridas[(corridas.concurrente == 1) & (corridas.calentamiento == 0)]
    filas = []
    for mecanismo in MECANISMOS:
        for tamano in TAMANOS:
            grupos = lat[(lat.mecanismo == mecanismo) & (lat.tamano == tamano)].groupby(["emisor", "receptor"])
            for (emisor, receptor), grupo in grupos:
                _, ic_media = media_e_intervalo(grupo.groupby("corrida").rtt_ms.mean())
                mps = cor[(cor.mecanismo == mecanismo) & (cor.tamano == tamano) & (cor.emisor == emisor)
                          & (cor.receptor == receptor)].mensajes_por_s
                filas.append({
                    "mecanismo": mecanismo, "tamano": tamano, "caracteres": int(grupo.caracteres.iloc[0]),
                    "emisor": emisor, "receptor": receptor, "n": len(grupo),
                    "media_ms": grupo.rtt_ms.mean(), "ic95_media_ms": ic_media,
                    "mediana_ms": grupo.rtt_ms.median(), "mensajes_por_s": mps.mean(),
                })
    return pd.DataFrame(filas)


def diferencias(est):
    """Diferencia porcentual (comparado - base) / base para tres comparaciones."""
    indice = est.set_index(["mecanismo", "tamano", "concurrente"])
    metricas = ["media_ms", "mediana_ms", "p95_ms", "mensajes_por_s", "mensajes_por_s_total"]
    filas = []

    def agregar(comparacion, base, comparado, **contexto):
        if base not in indice.index or comparado not in indice.index:
            return
        fila = {"comparacion": comparacion, **contexto}
        for metrica in metricas:
            b, c = indice.loc[base, metrica], indice.loc[comparado, metrica]
            fila[f"{metrica}_base"], fila[f"{metrica}_comparado"] = b, c
            fila[f"{metrica}_dif_pct"] = (c - b) / b * 100
        fila["razon_media"] = indice.loc[comparado, "media_ms"] / indice.loc[base, "media_ms"]
        filas.append(fila)

    for tamano in TAMANOS:
        for concurrente in PRUEBAS:
            agregar("grpc_vs_sockets", ("sockets", tamano, concurrente), ("grpc", tamano, concurrente),
                    tamano=tamano, concurrente=concurrente)
    for mecanismo in MECANISMOS:
        for concurrente in PRUEBAS:
            agregar("largo_vs_corto", (mecanismo, "corto", concurrente), (mecanismo, "largo", concurrente),
                    mecanismo=mecanismo, concurrente=concurrente)
        for tamano in TAMANOS:
            agregar("concurrente_vs_secuencial", (mecanismo, tamano, 0), (mecanismo, tamano, 1),
                    mecanismo=mecanismo, tamano=tamano)
    return pd.DataFrame(filas)


# ---------------------------------------------------------------- tablas LaTeX

def num(valor, decimales=3):
    if valor is None or (isinstance(valor, float) and math.isnan(valor)):
        return "--"
    texto = f"{valor:,.{decimales}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", "\\,")


def pct(valor):
    signo = "$-$" if valor < 0 else "+"
    return f"{signo}{num(abs(valor), 1)}\\,\\%"


def escapar(texto):
    reemplazos = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
                  "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return "".join(reemplazos.get(caracter, caracter) for caracter in str(texto))


def tabla(columnas, encabezado, filas):
    """Tabla con booktabs: `encabezado` son líneas LaTeX ya armadas; en `filas`, None deja un espacio."""
    lineas = ["% Generado por analysis/analizar.py a partir de data/. No editar a mano.",
              f"\\begin{{tabular}}{{{columnas}}}", "\\toprule", *encabezado, "\\midrule"]
    for fila in filas:
        lineas.append("\\addlinespace" if fila is None else " & ".join(fila) + " \\\\")
    lineas += ["\\bottomrule", "\\end{tabular}", ""]
    return "\n".join(lineas)


def tablas_latex(est, dif, condiciones, carpeta):
    carpeta.mkdir(parents=True, exist_ok=True)
    por_tamano = dict(zip(est.tamano, est.caracteres))

    def caracteres(tamano):
        return num(por_tamano[tamano], 0)

    def clientes(concurrente):
        return "3" if concurrente else "1"

    filas = []
    for i, mecanismo in enumerate(MECANISMOS):
        if i:
            filas.append(None)
        for f in est[est.mecanismo == mecanismo].itertuples():
            filas.append([MECANISMOS[f.mecanismo], num(f.caracteres, 0), str(f.clientes), num(f.n, 0),
                          f"{num(f.media_ms)} $\\pm$ {num(f.ic95_media_ms)}", num(f.mediana_ms), num(f.de_ms),
                          num(f.p95_ms), num(f.mensajes_por_s, 0)])
    (carpeta / "estadisticas.tex").write_text(tabla("lrrrrrrrr", [
        " & & & & \\multicolumn{4}{c}{Latencia de ida y vuelta (ms)} & Mensajes/s \\\\",
        "\\cmidrule(lr){5-8}",
        "Mecanismo & Caracteres & Clientes & $n$ & Media $\\pm$ IC 95\\,\\% & Mediana & DE & P95 & por cliente \\\\",
    ], filas), encoding="utf-8")

    grpc = dif[dif.comparacion == "grpc_vs_sockets"]
    (carpeta / "diferencias.tex").write_text(tabla("rrrrrrr", [
        " & & \\multicolumn{3}{c}{Latencia} & Mensajes/s & Media gRPC / \\\\",
        "\\cmidrule(lr){3-5}",
        "Caracteres & Clientes & Media & Mediana & P95 & por cliente & media sockets \\\\",
    ], [[caracteres(f.tamano), clientes(f.concurrente), pct(f.media_ms_dif_pct), pct(f.mediana_ms_dif_pct),
         pct(f.p95_ms_dif_pct), pct(f.mensajes_por_s_dif_pct), f"{num(f.razon_media, 1)} veces"]
        for f in grpc.itertuples()]), encoding="utf-8")

    tam = dif[dif.comparacion == "largo_vs_corto"]
    (carpeta / "tamano.tex").write_text(tabla("lrrrrr", [
        " & & \\multicolumn{3}{c}{Latencia media (ms)} & Mensajes/s \\\\",
        "\\cmidrule(lr){3-5}",
        "Mecanismo & Clientes & 100 caracteres & 10\\,000 caracteres & Cambio & cambio \\\\",
    ], [[MECANISMOS[f.mecanismo], clientes(f.concurrente), num(f.media_ms_base), num(f.media_ms_comparado),
         pct(f.media_ms_dif_pct), pct(f.mensajes_por_s_dif_pct)] for f in tam.itertuples()]), encoding="utf-8")

    con = dif[dif.comparacion == "concurrente_vs_secuencial"]
    (carpeta / "concurrencia.tex").write_text(tabla("lrrrrrrr", [
        " & & \\multicolumn{3}{c}{Latencia media (ms)} & \\multicolumn{3}{c}{Mensajes/s de todos los clientes} \\\\",
        "\\cmidrule(lr){3-5}\\cmidrule(lr){6-8}",
        "Mecanismo & Caracteres & 1 cliente & 3 clientes & Cambio & 1 cliente & 3 clientes & Cambio \\\\",
    ], [[MECANISMOS[f.mecanismo], caracteres(f.tamano), num(f.media_ms_base), num(f.media_ms_comparado),
         pct(f.media_ms_dif_pct), num(f.mensajes_por_s_total_base, 0), num(f.mensajes_por_s_total_comparado, 0),
         pct(f.mensajes_por_s_total_dif_pct)] for f in con.itertuples()]), encoding="utf-8")

    if condiciones:
        (carpeta / "condiciones.tex").write_text(tabla_condiciones(condiciones), encoding="utf-8")


def tabla_por_cliente(pc):
    filas = []
    for i, mecanismo in enumerate(MECANISMOS):
        if i:
            filas.append(None)
        for f in pc[pc.mecanismo == mecanismo].itertuples():
            filas.append([MECANISMOS[f.mecanismo], num(f.caracteres, 0), flechas(f"{f.emisor} -> {f.receptor}"),
                          f"{num(f.media_ms)} $\\pm$ {num(f.ic95_media_ms)}", num(f.mediana_ms),
                          num(f.mensajes_por_s, 0)])
    return tabla("lrlrrr", [
        " & & & \\multicolumn{2}{c}{Latencia (ms)} & \\\\",
        "\\cmidrule(lr){4-5}",
        "Mecanismo & Caracteres & Cliente & Media $\\pm$ IC 95\\,\\% & Mediana & Mensajes/s \\\\",
    ], filas)


def tabla_condiciones(c):
    protocolo = c.get("protocolo", {})
    bytes_mensaje = c.get("bytes_por_mensaje", {})
    librerias = ", ".join(f"{nombre} {version}" for nombre, version in c.get("librerias", {}).items())
    tamanos = "; ".join(
        f"{num(datos['caracteres'], 0)} caracteres: {num(datos.get('sockets_json_con_cabecera', math.nan), 0)} B "
        f"en JSON con su cabecera y {num(datos.get('grpc_protobuf', math.nan), 0)} B en Protocol Buffers"
        for datos in bytes_mensaje.values())
    inicio = datetime.fromisoformat(c["fecha_inicio"])
    fin = datetime.fromisoformat(c["fecha_fin"]) if c.get("fecha_fin") else None
    fecha = f"{inicio:%d/%m/%Y}, de {inicio:%H:%M:%S}" + (f" a {fin:%H:%M:%S}" if fin else "")
    memoria = f"{num(c.get('memoria_total_gb'), 1)} GB ({num(c.get('memoria_disponible_al_inicio_gb'), 1)} GB libres al empezar)"
    filas = [
        ["Fecha de la ejecución", escapar(fecha)],
        ["Sistema operativo", escapar(c.get("sistema_operativo", ""))],
        ["Procesador", escapar(f"{c.get('procesador', '')}, {c.get('nucleos_logicos', '')} núcleos lógicos")],
        ["Memoria", memoria],
        ["Plan de energía", escapar(c.get("plan_de_energia") or "no registrado")],
        ["Python y librerías", escapar(f"{c.get('python', '')}; {librerias}")],
        ["Despliegue", escapar(c.get("despliegue", ""))],
        ["Repeticiones", escapar(f"{protocolo.get('corridas_de_calentamiento')} corrida de calentamiento y "
                                 f"{protocolo.get('corridas')} corridas de {protocolo.get('envios_por_corrida')} "
                                 f"envíos por tamaño y mecanismo")],
        ["Tamaños de mensaje", tamanos],
        ["Un cliente", flechas(protocolo.get("latencia", ""))],
        ["Tres clientes a la vez", flechas(", ".join(protocolo.get("concurrencia", [])))],
    ]
    if c.get("notas"):
        filas.append(["Notas de quien ejecutó", escapar(c["notas"])])
    return tabla("lp{0.62\\linewidth}", ["Condición & Valor \\\\"], filas)


def flechas(texto):
    return escapar(texto).replace("->", "$\\rightarrow$")


# ---------------------------------------------------------------- gráficos

def estilo():
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 9, "axes.titlesize": 9.5, "axes.labelsize": 9,
        "xtick.labelsize": 8.5, "ytick.labelsize": 8.5, "legend.fontsize": 8.5,
        "axes.edgecolor": EJE, "axes.linewidth": 0.8, "axes.labelcolor": TINTA_2, "axes.titlecolor": TINTA,
        "xtick.color": EJE, "ytick.color": EJE, "xtick.labelcolor": TINTA_2, "ytick.labelcolor": TINTA_2,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "axes.grid.axis": "y", "grid.color": REJILLA, "grid.linewidth": 0.6,
        "grid.linestyle": "-", "axes.axisbelow": True, "legend.frameon": False,
        "figure.facecolor": "white", "axes.facecolor": "white", "savefig.facecolor": "white",
        "pdf.fonttype": 42,
    })


def formato_ms(valor, _=None):
    return f"{valor:g}".replace(".", ",")


def etiqueta_ms(valor):
    return f"{valor:.3f}".replace(".", ",")


def formato_miles(valor, _=None):
    return f"{valor:,.0f}".replace(",", " ")


def piso_logaritmico(valor):
    """Mayor valor de la serie 1-2-5 que queda por debajo de `valor`, para que el eje empiece en una marca."""
    potencia = 10.0 ** math.floor(math.log10(valor))
    for factor in (5, 2, 1):
        if factor * potencia <= valor:
            return factor * potencia
    return potencia


def leyenda(figura):
    marcas = [Patch(facecolor=COLOR[m], edgecolor="none", label=etiqueta) for m, etiqueta in MECANISMOS.items()]
    figura.legend(handles=marcas, loc="upper right", ncol=2, bbox_to_anchor=(0.99, 1.06),
                  handlelength=1.0, handleheight=1.0, columnspacing=1.4)


def titular(eje, concurrente):
    eje.set_title(f"{PRUEBAS[concurrente]}\n", loc="left", fontweight="bold")
    eje.text(0, 1.02, SUBTITULOS[concurrente], transform=eje.transAxes, fontsize=8, color=TINTA_2, va="bottom")


def guardar(figura, carpeta, nombre):
    carpeta.mkdir(parents=True, exist_ok=True)
    figura.savefig(carpeta / f"{nombre}.pdf", bbox_inches="tight", metadata={"CreationDate": None})
    figura.savefig(carpeta / f"{nombre}.png", bbox_inches="tight", dpi=200)
    plt.close(figura)


def figura_cajas(latencias, carpeta):
    validas = latencias[latencias.calentamiento == 0]
    figura, ejes = plt.subplots(1, len(PRUEBAS), figsize=(6.8, 3.3), sharey=True)
    for eje, concurrente in zip(ejes, PRUEBAS):
        for i, tamano in enumerate(TAMANOS):
            for j, mecanismo in enumerate(MECANISMOS):
                valores = validas[(validas.mecanismo == mecanismo) & (validas.tamano == tamano)
                                  & (validas.concurrente == concurrente)].rtt_ms
                if valores.empty:
                    continue
                color = COLOR[mecanismo]
                eje.boxplot([valores.to_numpy()], positions=[i + (j - 0.5) * 0.3], widths=0.24,
                            patch_artist=True, whis=1.5,
                            boxprops={"facecolor": to_rgba(color, 0.18), "edgecolor": color, "linewidth": 1.1},
                            medianprops={"color": color, "linewidth": 2},
                            whiskerprops={"color": color, "linewidth": 1}, capprops={"color": color, "linewidth": 1},
                            flierprops={"marker": "o", "markersize": 2.2, "markeredgecolor": "none",
                                        "markerfacecolor": to_rgba(color, 0.35)})
        eje.set_xticks(range(len(TAMANOS)), list(TAMANOS.values()))
        eje.set_xlim(-0.6, len(TAMANOS) - 0.4)
        eje.tick_params(axis="x", length=0)
        eje.set_yscale("log")
        eje.yaxis.set_major_locator(LogLocator(subs=(1.0, 2.0, 5.0)))
        eje.yaxis.set_major_formatter(FuncFormatter(formato_ms))
        eje.yaxis.set_minor_formatter(NullFormatter())
        titular(eje, concurrente)
    ejes[0].set_ylim(bottom=piso_logaritmico(validas.rtt_ms.min()))
    ejes[0].set_ylabel("Latencia de ida y vuelta (ms, escala log.)")
    leyenda(figura)
    figura.tight_layout()
    guardar(figura, carpeta, "cajas_latencia")


def figura_barras(est, columna, columna_ic, etiqueta_y, formato, etiqueta, nombre, carpeta):
    figura, ejes = plt.subplots(1, len(PRUEBAS), figsize=(6.8, 3.1), sharey=True)
    ancho = 0.26
    for eje, concurrente in zip(ejes, PRUEBAS):
        for j, mecanismo in enumerate(MECANISMOS):
            filas = (est[(est.mecanismo == mecanismo) & (est.concurrente == concurrente)]
                     .set_index("tamano").reindex(list(TAMANOS)))
            x = np.arange(len(TAMANOS)) + (j - 0.5) * (ancho + 0.03)
            valores = filas[columna].to_numpy(dtype=float)
            errores = filas[columna_ic].fillna(0).to_numpy(dtype=float)
            eje.bar(x, valores, width=ancho, color=COLOR[mecanismo], zorder=2)
            eje.errorbar(x, valores, yerr=errores, fmt="none", ecolor=TINTA, elinewidth=1, capsize=3,
                         capthick=1, zorder=3)
            for xi, valor, error in zip(x, valores, errores):
                if not math.isnan(valor):
                    eje.annotate(etiqueta(valor), (xi, valor + error), xytext=(0, 3), textcoords="offset points",
                                 ha="center", va="bottom", fontsize=7.5, color=TINTA_2)
        eje.set_xticks(range(len(TAMANOS)), list(TAMANOS.values()))
        eje.set_xlim(-0.6, len(TAMANOS) - 0.4)
        eje.tick_params(axis="x", length=0)
        eje.yaxis.set_major_formatter(FuncFormatter(formato))
        eje.margins(y=0.14)
        titular(eje, concurrente)
    ejes[0].set_ylabel(etiqueta_y)
    leyenda(figura)
    figura.tight_layout()
    guardar(figura, carpeta, nombre)


# ---------------------------------------------------------------- consola

def imprimir(est, dif):
    print(f"\n{'Mecanismo':12} {'Caract.':>7}  {'Prueba':22} {'n':>5} {'Media':>8} {'IC95':>7} {'Mediana':>8} "
          f"{'DE':>7} {'P95':>7} {'Msj/s':>8}")
    for f in est.itertuples():
        print(f"{MECANISMOS[f.mecanismo]:12} {f.caracteres:>7}  {PRUEBAS[f.concurrente]:22} {f.n:>5} "
              f"{f.media_ms:8.3f} {f.ic95_media_ms:7.3f} {f.mediana_ms:8.3f} {f.de_ms:7.3f} {f.p95_ms:7.3f} "
              f"{f.mensajes_por_s:8.0f}")
    print("Latencias en ms; mensajes/s por cliente; IC95 = semiancho del intervalo de confianza de la media.\n")
    for f in dif[dif.comparacion == "grpc_vs_sockets"].itertuples():
        print(f"gRPC frente a sockets, {TAMANOS[f.tamano]}, {PRUEBAS[f.concurrente].lower()}: "
              f"media {f.media_ms_dif_pct:+.1f} % ({f.razon_media:.1f} veces), "
              f"mensajes/s {f.mensajes_por_s_dif_pct:+.1f} %")


def main():
    parser = argparse.ArgumentParser(description="Análisis de latencia y rendimiento de la PE-U1")
    parser.add_argument("--datos", default=str(RAIZ / "data"), help="carpeta con los CSV")
    parser.add_argument("--salida", default=str(RAIZ / "analysis"), help="carpeta de resultados, tablas y figuras")
    args = parser.parse_args()
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(errors="replace")
        except AttributeError:
            pass

    datos, salida = Path(args.datos).resolve(), Path(args.salida).resolve()
    print(f"Análisis PE-U1 | datos: {datos} | {datetime.now():%Y-%m-%d %H:%M:%S}")
    comprobar_sumas(datos)
    latencias = cargar(datos, "latencia_*.csv")
    corridas = cargar(datos, "corridas_*.csv")
    ruta_condiciones = datos / "condiciones.json"
    condiciones = json.loads(ruta_condiciones.read_text(encoding="utf-8")) if ruta_condiciones.exists() else None
    calentamiento = int(latencias.calentamiento.sum())
    print(f"Mediciones: {len(latencias)} filas en los CSV; {calentamiento} son de calentamiento y no se usan.")

    est = estadisticas(latencias, corridas)
    dif = diferencias(est)
    (salida / "resultados").mkdir(parents=True, exist_ok=True)
    est.to_csv(salida / "resultados" / "estadisticas.csv", index=False, float_format="%.6f")
    dif.to_csv(salida / "resultados" / "diferencias.csv", index=False, float_format="%.6f")
    tablas_latex(est, dif, condiciones, salida / "tablas")
    pc = por_cliente(latencias, corridas)
    if not pc.empty:
        pc.to_csv(salida / "resultados" / "por_cliente.csv", index=False, float_format="%.6f")
        (salida / "tablas" / "por_cliente.tex").write_text(tabla_por_cliente(pc), encoding="utf-8")

    estilo()
    figura_cajas(latencias, salida / "figuras")
    figura_barras(est, "media_ms", "ic95_media_ms", "Latencia media (ms) e IC del 95 %",
                  formato_ms, etiqueta_ms, "barras_latencia", salida / "figuras")
    figura_barras(est, "mensajes_por_s", "ic95_mensajes_por_s", "Mensajes/s por cliente e IC del 95 %",
                  formato_miles, formato_miles, "barras_rendimiento", salida / "figuras")

    imprimir(est, dif)
    print(f"\nEscrito en {salida}: resultados/ (3 CSV), tablas/ (6 .tex) y figuras/ (3 gráficos en PDF y PNG).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

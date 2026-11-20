r"""Verificación del reloj de Lamport con los CSV reales del escenario de 20 intercambios.

Uso, desde la raíz del repositorio:   python analysis\verificar_lamport.py

Lee data/eventos_<mecanismo>_nodo-X.csv (no genera ni simula datos) y, para sockets y para gRPC, comprueba:
  1. las reglas del reloj en cada nodo: un envío suma 1 y una recepción toma max(local, recibido) + 1;
  2. que cada recepción tiene su envío (el emisor y el valor del reloj que viajó en el mensaje) y que
     el reloj al recibir es mayor que el reloj al enviar;
  3. la relación «sucedió antes» (el orden dentro de cada nodo más los mensajes): si a -> b, C(a) < C(b).
Además busca los pares de eventos concurrentes, que ninguna cadena de mensajes une, y entre ellos
los que tienen el mismo valor de reloj.
Escribe analysis/resultados/lamport_<mecanismo>.txt, analysis/tablas/lamport_<mecanismo>.tex y el
diagrama espacio-tiempo analysis/figuras/lamport_<mecanismo>.pdf y .png. Termina con código 1 si algo falla.
"""

import argparse
import sys
from collections import defaultdict
from datetime import datetime
from itertools import combinations
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.ticker import MultipleLocator  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from src.comun import config, escenario  # noqa: E402

MECANISMOS = {"sockets": "Sockets TCP", "grpc": "gRPC"}
TINTA, TINTA_2, TINTA_3 = "#0b0b0b", "#52514e", "#898781"
EJE, DESTACADO = "#c3c2b7", "#6250d6"
PASO = {(origen, destino, texto): numero for numero, origen, destino, texto, _ in escenario.PASOS}


def cargar(datos, mecanismo):
    archivos = sorted(datos.glob(f"eventos_{mecanismo}_nodo-*.csv"))
    if not archivos:
        return None, []
    eventos = pd.concat([pd.read_csv(archivo) for archivo in archivos], ignore_index=True)
    eventos["reloj"] = eventos["reloj"].astype(int)
    eventos["reloj_mensaje"] = eventos["reloj_mensaje"].astype(int)
    return eventos, [archivo.name for archivo in archivos]


def verificar(eventos):
    fallos = []
    repetidos = eventos[eventos.duplicated(["nodo", "reloj"], keep=False)]
    for fila in repetidos.itertuples(index=False):
        fallos.append(f"{fila.nodo} tiene dos eventos con reloj {fila.reloj}")

    # 1. Reglas del reloj dentro de cada nodo, en el orden en que ocurrieron.
    orden = {}
    for nodo, grupo in eventos.groupby("nodo"):
        anterior = 0
        for fila in grupo.sort_values("reloj").itertuples(index=False):
            esperado = anterior + 1 if fila.evento == "envio" else max(anterior, fila.reloj_mensaje) + 1
            if fila.reloj != esperado:
                fallos.append(f"{nodo}: el {fila.evento} con reloj {fila.reloj} debía tener {esperado}")
            anterior = fila.reloj
        orden[nodo] = [(nodo, reloj) for reloj in sorted(grupo.reloj)]

    # 2. Cada recepción con su envío: mismo emisor y mismo valor de reloj en el mensaje.
    envios = {(f.nodo, f.reloj): f for f in eventos[eventos.evento == "envio"].itertuples(index=False)}
    mensajes, usados = [], set()
    for r in eventos[eventos.evento == "recepcion"].itertuples(index=False):
        e = envios.get((r.origen, r.reloj_mensaje))
        if e is None or e.destino != r.nodo or e.mensaje != r.mensaje:
            fallos.append(f"{r.nodo} recibió con reloj {r.reloj} un mensaje sin envío que coincida")
            continue
        usados.add((e.nodo, e.reloj))
        if not r.reloj > e.reloj:
            fallos.append(f"{e.nodo} -> {r.nodo}: reloj al recibir {r.reloj} no es mayor que al enviar {e.reloj}")
        paso = PASO.get((config.letra_de(e.nodo), config.letra_de(r.nodo), e.mensaje))
        mensajes.append((paso, e, r))
    for clave in sorted(envios.keys() - usados):
        fallos.append(f"el envío de {clave[0]} con reloj {clave[1]} no tiene recepción")
    mensajes.sort(key=lambda m: (m[0] is None, m[0] or 0, m[1].reloj))

    # 3. Sucedió antes: orden de cada nodo más los mensajes, cerrado por transitividad.
    sucesores = defaultdict(set)
    for ids in orden.values():
        for a, b in zip(ids, ids[1:]):
            sucesores[a].add(b)
    for _, e, r in mensajes:
        sucesores[(e.nodo, e.reloj)].add((r.nodo, r.reloj))
    todos = [i for ids in orden.values() for i in ids]
    alcanza = {}
    for inicio in todos:
        vistos, pendientes = set(), [inicio]
        while pendientes:
            for siguiente in sucesores[pendientes.pop()]:
                if siguiente not in vistos:
                    vistos.add(siguiente)
                    pendientes.append(siguiente)
        alcanza[inicio] = vistos
    ordenados = [(a, b) for a in todos for b in alcanza[a]]
    for a, b in ordenados:
        if not a[1] < b[1]:
            fallos.append(f"{a} sucedió antes que {b} pero su reloj no es menor")
    concurrentes = [(a, b) for a, b in combinations(todos, 2) if b not in alcanza[a] and a not in alcanza[b]]
    iguales = [(a, b) for a, b in concurrentes if a[1] == b[1]]
    return {"fallos": fallos, "mensajes": mensajes, "ordenados": ordenados,
            "concurrentes": concurrentes, "iguales": iguales}


def describir(eventos, evento_id):
    fila = eventos[(eventos.nodo == evento_id[0]) & (eventos.reloj == evento_id[1])].iloc[0]
    accion = f"envío a {fila.destino}" if fila.evento == "envio" else f"recepción desde {fila.origen}"
    return f"{fila.nodo}, {accion}, reloj {fila.reloj}: «{fila.mensaje}»"


def informe(mecanismo, archivos, eventos, r):
    envios = int((eventos.evento == "envio").sum())
    recepciones = len(eventos) - envios
    diferencias = [rec.reloj - env.reloj for _, env, rec in r["mensajes"]]
    lineas = [
        f"Verificación del reloj de Lamport | {MECANISMOS[mecanismo]} | {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"Datos: {', '.join(archivos)}",
        f"Eventos: {len(eventos)} ({envios} envíos y {recepciones} recepciones) en {eventos.nodo.nunique()} nodos",
        "1. Reglas del reloj en cada nodo (envío: local + 1; recepción: max(local, recibido) + 1): "
        + ("se cumplen en todos los eventos" if not any("debía tener" in f for f in r["fallos"]) else "FALLAN"),
        f"2. Mensajes emparejados: {len(r['mensajes'])} de {recepciones} recepciones tienen su envío; "
        + ((f"en todas, el reloj al recibir es mayor que el reloj al enviar (diferencia de {min(diferencias)} "
            f"a {max(diferencias)})") if diferencias and not any("no es mayor" in f for f in r["fallos"])
           else "hay recepciones con reloj menor o igual al del envío"),
        f"3. Pares de eventos ordenados por «sucedió antes»: {len(r['ordenados'])}; "
        + ("en todos C(a) < C(b)" if not any("sucedió antes" in f for f in r["fallos"]) else "hay violaciones"),
        f"Pares concurrentes (ninguno sucedió antes que el otro): {len(r['concurrentes'])}; "
        f"con el mismo valor de reloj: {len(r['iguales'])}",
    ]
    for a, b in r["iguales"]:
        lineas += [f"   - {describir(eventos, a)}", f"     {describir(eventos, b)}"]
    distintos = [(a, b) for a, b in r["concurrentes"] if a[1] != b[1]]
    if distintos:
        a, b = distintos[0]
        lineas += [f"Concurrentes con relojes distintos: {len(distintos)}. Por ejemplo:",
                   f"   - {describir(eventos, a)}", f"     {describir(eventos, b)}"]
    for fallo in r["fallos"]:
        lineas.append(f"FALLA: {fallo}")
    lineas.append("Resultado: " + ("CORRECTO" if not r["fallos"] else f"{len(r['fallos'])} FALLAS"))
    return lineas


def tabla_latex(r, iguales_ids):
    lineas = ["% Generado por analysis/verificar_lamport.py a partir de data/. No editar a mano.",
              "\\begin{tabular}{rlrrp{0.42\\linewidth}}", "\\toprule",
              " & & Reloj al & Reloj al & \\\\",
              "Paso & Emisor $\\rightarrow$ receptor & enviar & recibir & Contenido del mensaje \\\\", "\\midrule"]
    for paso, e, rec in r["mensajes"]:
        marca = "$^{*}$" if (e.nodo, e.reloj) in iguales_ids else ""
        texto = str(e.mensaje).replace("\\", "").replace("&", "\\&").replace("%", "\\%").replace("_", "\\_")
        lineas.append(f"{paso if paso else '--'} & {e.nodo} $\\rightarrow$ {rec.nodo} & {e.reloj}{marca} & "
                      f"{rec.reloj} & {texto} \\\\")
    lineas += ["\\bottomrule", "\\end{tabular}", ""]
    return "\n".join(lineas)


def diagrama(eventos, r, mecanismo, carpeta):
    nodos = sorted(eventos.nodo.unique())
    y = {nodo: len(nodos) - 1 - i for i, nodo in enumerate(nodos)}
    maximo = int(eventos.reloj.max())
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "pdf.fonttype": 42})
    figura, eje = plt.subplots(figsize=(6.8, 2.4))
    for nodo, altura in y.items():
        eje.plot([0.4, maximo + 0.8], [altura, altura], color=EJE, linewidth=1, zorder=1)
    for paso, e, rec in r["mensajes"]:
        eje.annotate("", xy=(rec.reloj, y[rec.nodo]), xytext=(e.reloj, y[e.nodo]), zorder=2,
                     arrowprops={"arrowstyle": "-|>", "color": TINTA_3, "linewidth": 0.8,
                                 "shrinkA": 3.5, "shrinkB": 3.5, "mutation_scale": 7})
        if paso:
            eje.text((e.reloj + rec.reloj) / 2, (y[e.nodo] + y[rec.nodo]) / 2, str(paso), fontsize=6.5,
                     color=TINTA_2, ha="center", va="center", zorder=3,
                     bbox={"boxstyle": "round,pad=0.12", "facecolor": "white", "edgecolor": "none"})
    eje.scatter(eventos.reloj, eventos.nodo.map(y), s=16, color=TINTA_2, edgecolors="white", linewidths=0.8,
                zorder=4)
    destacados = sorted({i for par in r["iguales"] for i in par})
    if destacados:
        eje.scatter([i[1] for i in destacados], [y[i[0]] for i in destacados], s=46, color=DESTACADO,
                    edgecolors="white", linewidths=1.2, zorder=5)
    eje.set_yticks(list(y.values()), list(y.keys()))
    eje.tick_params(axis="y", length=0, labelsize=9, labelcolor=TINTA)
    eje.tick_params(axis="x", color=EJE, labelcolor=TINTA_2, labelsize=8.5)
    eje.xaxis.set_major_locator(MultipleLocator(5))
    eje.set_xlim(0, maximo + 1)
    eje.set_ylim(-0.45, len(nodos) - 0.55)
    eje.set_xlabel("Valor del reloj de Lamport", color=TINTA_2)
    for lado in ("top", "right", "left"):
        eje.spines[lado].set_visible(False)
    eje.spines["bottom"].set_color(EJE)
    marcas = [Line2D([], [], marker="o", linestyle="none", markersize=4.5, color=TINTA_2,
                     markeredgecolor="white", label="Evento (envío o recepción); la flecha es el mensaje"),
              Line2D([], [], marker="o", linestyle="none", markersize=7, color=DESTACADO,
                     markeredgecolor="white", label="Concurrentes con el mismo valor de reloj")]
    eje.legend(handles=marcas, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, frameon=False, fontsize=8,
               handletextpad=0.3, columnspacing=1.5, borderaxespad=0.2)
    carpeta.mkdir(parents=True, exist_ok=True)
    figura.savefig(carpeta / f"lamport_{mecanismo}.pdf", bbox_inches="tight", metadata={"CreationDate": None})
    figura.savefig(carpeta / f"lamport_{mecanismo}.png", bbox_inches="tight", dpi=200)
    plt.close(figura)


def main():
    parser = argparse.ArgumentParser(description="Verificación del reloj de Lamport con los CSV de eventos")
    parser.add_argument("--datos", default=str(RAIZ / "data"), help="carpeta con los CSV de eventos")
    parser.add_argument("--salida", default=str(RAIZ / "analysis"), help="carpeta de resultados, tablas y figuras")
    args = parser.parse_args()
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(errors="replace")
        except AttributeError:
            pass
    datos, salida = Path(args.datos).resolve(), Path(args.salida).resolve()

    revisados, con_fallas = 0, 0
    for mecanismo in MECANISMOS:
        eventos, archivos = cargar(datos, mecanismo)
        if eventos is None:
            print(f"No hay eventos de {MECANISMOS[mecanismo]} en {datos}.\n")
            continue
        resultado = verificar(eventos)
        lineas = informe(mecanismo, archivos, eventos, resultado)
        print("\n".join(lineas) + "\n")
        (salida / "resultados").mkdir(parents=True, exist_ok=True)
        (salida / "resultados" / f"lamport_{mecanismo}.txt").write_text("\n".join(lineas) + "\n", encoding="utf-8")
        (salida / "tablas").mkdir(parents=True, exist_ok=True)
        iguales = {i for par in resultado["iguales"] for i in par}
        (salida / "tablas" / f"lamport_{mecanismo}.tex").write_text(tabla_latex(resultado, iguales), encoding="utf-8")
        diagrama(eventos, resultado, mecanismo, salida / "figuras")
        revisados += 1
        con_fallas += bool(resultado["fallos"])
    if not revisados:
        print("Primero ejecuta los nodos o: python -m src.ejecutar_experimento")
        return 1
    return 1 if con_fallas else 0


if __name__ == "__main__":
    sys.exit(main())

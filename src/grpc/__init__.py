"""El código generado por grpcio-tools importa `mensajeria_pb2` sin paquete; por eso esta carpeta
se agrega a la ruta de búsqueda antes de usarlo."""

import sys
from pathlib import Path

_CARPETA = str(Path(__file__).resolve().parent)
if _CARPETA not in sys.path:
    sys.path.append(_CARPETA)

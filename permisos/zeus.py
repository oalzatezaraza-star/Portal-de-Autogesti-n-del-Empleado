"""Lectura de empleados desde Zeus Reloj (solo lectura).

El portal nunca escribe en Zeus. Hay dos formas de leerlo; cuál usar depende de
lo que confirme el proveedor:

* ZeusCSV: Zeus (o un proceso del proveedor) exporta un CSV periódicamente.
  Es lo más simple y no toca la base de Zeus.
* ZeusSQL: consulta directa de solo lectura (p. ej. SQL Server por ODBC). Antes
  de usarla, confirma con el proveedor que no afecta soporte ni garantía y pide
  un usuario de BD con permiso SELECT únicamente, sobre vistas si es posible.

Ambas devuelven `EmpleadoZeus`. Los nombres de columnas de Zeus son un supuesto:
ajústalos cuando tengas la documentación real.
"""
import csv
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Iterable, Optional

from django.conf import settings


@dataclass
class EmpleadoZeus:
    cedula: str
    nombre: str
    cargo: str = ""
    area: str = ""
    seccion: str = ""
    email: str = ""
    jefe_cedula: str = ""
    activo: bool = True
    horario_inicio: Optional[time] = None
    horario_fin: Optional[time] = None
    fecha_ingreso: Optional[date] = None


def _hora(valor):
    valor = (valor or "").strip()
    if not valor:
        return None
    horas, minutos = valor.split(":")[:2]
    return time(int(horas), int(minutos))


def _fecha(valor):
    """Acepta date/datetime (ODBC) o texto AAAA-MM-DD / DD/MM/AAAA (CSV)."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    valor = (valor or "").strip()
    if not valor:
        return None
    if "/" in valor:
        d, m, a = valor.split("/")
        return date(int(a), int(m), int(d))
    return date.fromisoformat(valor[:10])


def _activo(valor):
    return str(valor).strip().lower() in {"1", "true", "si", "sí", "activo", "a", "s"}


def _desde_fila(f):
    return EmpleadoZeus(
        cedula=str(f["cedula"]).strip(),
        nombre=str(f["nombre"]).strip(),
        cargo=(f.get("cargo") or "").strip(),
        area=(f.get("area") or "").strip(),
        seccion=(f.get("seccion") or "").strip(),
        email=(f.get("email") or "").strip(),
        jefe_cedula=str(f.get("jefe_cedula") or "").strip(),
        activo=_activo(f.get("activo", "1")),
        horario_inicio=_hora(f.get("horario_inicio")),
        horario_fin=_hora(f.get("horario_fin")),
        fecha_ingreso=_fecha(f.get("fecha_ingreso")),
    )


class ZeusCSV:
    """Columnas esperadas: cedula,nombre,cargo,area,seccion,email,jefe_cedula,activo,
    horario_inicio,horario_fin,fecha_ingreso (las tres últimas son opcionales)."""

    def __init__(self, ruta):
        self.ruta = ruta

    def listar(self) -> Iterable[EmpleadoZeus]:
        with open(self.ruta, newline="", encoding="utf-8-sig") as archivo:
            for fila in csv.DictReader(archivo):
                yield _desde_fila(fila)


class ZeusSQL:
    """Ejecuta ZEUS_SQL_QUERY, que debe devolver las mismas columnas que el CSV
    (con alias). Ejemplo, ajustando tablas y campos a Zeus:

        SELECT e.Identificacion AS cedula, e.NombreCompleto AS nombre,
               e.Cargo AS cargo, e.Dependencia AS area, '' AS seccion,
               e.Correo AS email, e.CedulaJefe AS jefe_cedula, e.FechaIngreso AS fecha_ingreso,
               CASE WHEN e.Estado = 'A' THEN 1 ELSE 0 END AS activo
        FROM dbo.Empleados e
    """

    def listar(self) -> Iterable[EmpleadoZeus]:
        import pyodbc  # se importa aquí para no exigirlo si se usa CSV

        if not (settings.ZEUS_ODBC_CONNECTION and settings.ZEUS_SQL_QUERY):
            raise RuntimeError("Faltan ZEUS_ODBC_CONNECTION y ZEUS_SQL_QUERY.")
        conexion = pyodbc.connect(settings.ZEUS_ODBC_CONNECTION, readonly=True, timeout=15)
        try:
            cursor = conexion.cursor()
            cursor.execute(settings.ZEUS_SQL_QUERY)
            columnas = [c[0] for c in cursor.description]
            for fila in cursor.fetchall():
                yield _desde_fila(dict(zip(columnas, fila)))
        finally:
            conexion.close()


def obtener_cliente():
    if settings.ZEUS_BACKEND == "sql":
        return ZeusSQL()
    return ZeusCSV(settings.ZEUS_CSV_PATH)

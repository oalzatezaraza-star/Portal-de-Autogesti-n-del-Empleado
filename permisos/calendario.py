"""Cálculos de calendario y de causación de vacaciones. Python puro, sin Django.

Todo lo que sea una regla de Gestión Humana (qué días cuentan como hábiles,
cuántos días por año, etc.) se recibe como parámetro; los valores por defecto
viven en settings.py y deben confirmarse con Gestión Humana o un asesor laboral.
"""
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache


def _pascua(anio):
    """Domingo de Pascua (algoritmo de Meeus/Jones/Butcher)."""
    a, b, c = anio % 19, anio // 100, anio % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = (h + l - 7 * m + 114) % 31 + 1
    return date(anio, mes, dia)


def _al_lunes(d):
    """Ley Emiliani: el festivo se traslada al lunes siguiente (si ya es lunes, se queda)."""
    return d + timedelta(days=(7 - d.weekday()) % 7)


@lru_cache(maxsize=None)
def festivos_colombia(anio):
    """Festivos nacionales de Colombia de un año."""
    pascua = _pascua(anio)
    fijos = [(1, 1), (5, 1), (7, 20), (8, 7), (12, 8), (12, 25)]
    trasladables = [(1, 6), (3, 19), (6, 29), (8, 15), (10, 12), (11, 1), (11, 11)]
    festivos = {date(anio, m, d) for m, d in fijos}
    festivos |= {_al_lunes(date(anio, m, d)) for m, d in trasladables}
    festivos |= {pascua - timedelta(days=3), pascua - timedelta(days=2)}  # Jueves y Viernes Santo
    festivos |= {_al_lunes(pascua + timedelta(days=n)) for n in (39, 60, 68)}  # Ascensión, Corpus, Sagrado Corazón
    return frozenset(festivos)


def es_dia_habil(d, dias_semana):
    """dias_semana: números de weekday() que cuentan (lunes=0 … domingo=6)."""
    return d.weekday() in dias_semana and d not in festivos_colombia(d.year)


def contar_dias_habiles(inicio, fin, dias_semana):
    if fin < inicio:
        return 0
    total, d = 0, inicio
    while d <= fin:
        total += es_dia_habil(d, dias_semana)
        d += timedelta(days=1)
    return total


def siguiente_dia_habil(d, dias_semana):
    """Primer día hábil posterior a `d` (fecha de reintegro después de vacaciones)."""
    for _ in range(14):
        d += timedelta(days=1)
        if es_dia_habil(d, dias_semana):
            return d
    return d


def dias_360(d1, d2):
    """Días entre dos fechas con el año comercial de 360 días (meses de 30)."""
    return (d2.year - d1.year) * 360 + (d2.month - d1.month) * 30 + (min(d2.day, 30) - min(d1.day, 30))


def dias_laborados(fecha_ingreso, hasta):
    """Días laborados, contando el de ingreso y el de corte (año comercial)."""
    return max(dias_360(fecha_ingreso, hasta) + 1, 0)


def dias_causados(fecha_ingreso, hasta, dias_por_anio=15):
    """Días de vacaciones causados: dias_por_anio por cada 360 días laborados."""
    laborados = dias_laborados(fecha_ingreso, hasta)
    return (Decimal(laborados) * Decimal(dias_por_anio) / Decimal(360)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def cumple_antiguedad(fecha_ingreso, fecha, minimo_dias=360):
    return dias_laborados(fecha_ingreso, fecha) >= minimo_dias

"""Pruebas de cálculo puro (no necesitan base de datos)."""
import unittest
from datetime import date
from decimal import Decimal

from . import calendario as c

LUN_SAB = {0, 1, 2, 3, 4, 5}
LUN_VIE = {0, 1, 2, 3, 4}


class CalendarioTests(unittest.TestCase):
    def test_festivos_2026(self):
        esperados = {
            date(2026, 1, 1), date(2026, 1, 12), date(2026, 3, 23), date(2026, 4, 2),
            date(2026, 4, 3), date(2026, 5, 1), date(2026, 5, 18), date(2026, 6, 8),
            date(2026, 6, 15), date(2026, 6, 29), date(2026, 7, 20), date(2026, 8, 7),
            date(2026, 8, 17), date(2026, 10, 12), date(2026, 11, 2), date(2026, 11, 16),
            date(2026, 12, 8), date(2026, 12, 25),
        }
        self.assertEqual(set(c.festivos_colombia(2026)), esperados)

    def test_cantidad_de_festivos_razonable(self):
        # 18 festivos, salvo años en que dos coinciden en la misma fecha (p. ej. 2025).
        for anio in range(2024, 2031):
            self.assertIn(len(c.festivos_colombia(anio)), (17, 18), anio)

    def test_2025_junio_30_coinciden_dos_festivos(self):
        self.assertIn(date(2025, 6, 30), c.festivos_colombia(2025))

    def test_dias_habiles_con_semana_santa(self):
        self.assertEqual(c.contar_dias_habiles(date(2026, 4, 1), date(2026, 4, 10), LUN_SAB), 7)
        self.assertEqual(c.contar_dias_habiles(date(2026, 4, 1), date(2026, 4, 10), LUN_VIE), 6)

    def test_rango_invertido_da_cero(self):
        self.assertEqual(c.contar_dias_habiles(date(2026, 4, 10), date(2026, 4, 1), LUN_SAB), 0)

    def test_reintegro_salta_domingo_y_festivo(self):
        # Viernes 8 de mayo de 2026 → reintegro sábado 9 (lun–sáb)
        self.assertEqual(c.siguiente_dia_habil(date(2026, 5, 8), LUN_SAB), date(2026, 5, 9))
        # Sábado 9 → el domingo no cuenta → lunes 11
        self.assertEqual(c.siguiente_dia_habil(date(2026, 5, 9), LUN_SAB), date(2026, 5, 11))
        # Sábado 16 de mayo → domingo 17 y lunes 18 (festivo) → martes 19
        self.assertEqual(c.siguiente_dia_habil(date(2026, 5, 16), LUN_SAB), date(2026, 5, 19))

    def test_un_anio_completo_causa_15_dias(self):
        self.assertEqual(c.dias_causados(date(2025, 1, 1), date(2025, 12, 31)), Decimal("15.00"))

    def test_seis_meses_causan_7_5_dias(self):
        self.assertEqual(c.dias_causados(date(2025, 1, 1), date(2025, 6, 30)), Decimal("7.50"))

    def test_antes_del_ingreso_no_causa(self):
        self.assertEqual(c.dias_causados(date(2025, 6, 1), date(2025, 1, 1)), Decimal("0.00"))

    def test_antiguedad_minima(self):
        self.assertFalse(c.cumple_antiguedad(date(2025, 1, 1), date(2025, 12, 29)))
        self.assertTrue(c.cumple_antiguedad(date(2025, 1, 1), date(2025, 12, 31)))


if __name__ == "__main__":
    unittest.main()

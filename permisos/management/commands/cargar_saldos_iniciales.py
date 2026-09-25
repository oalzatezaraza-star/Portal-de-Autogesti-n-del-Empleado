import csv
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from permisos.models import AjusteVacaciones, Empleado


class Command(BaseCommand):
    help = (
        "Carga los días de vacaciones ya disfrutados (o compensados) antes de usar el portal. "
        "CSV con columnas: cedula,dias_previos[,motivo]. Cada fila crea un ajuste NEGATIVO."
    )

    def add_arguments(self, parser):
        parser.add_argument("archivo")

    @transaction.atomic
    def handle(self, *args, archivo, **opciones):
        creados, errores = 0, []
        with open(archivo, newline="", encoding="utf-8-sig") as f:
            for n, fila in enumerate(csv.DictReader(f), start=2):
                cedula = (fila.get("cedula") or "").strip()
                try:
                    dias = Decimal((fila.get("dias_previos") or "").strip())
                    emp = Empleado.objects.get(cedula=cedula)
                except (InvalidOperation, Empleado.DoesNotExist):
                    errores.append(f"fila {n} (cédula {cedula or '?'})")
                    continue
                if dias == 0:
                    continue
                AjusteVacaciones.objects.create(
                    empleado=emp, dias=-abs(dias),
                    motivo=(fila.get("motivo") or "Días disfrutados antes del portal").strip()[:200],
                )
                creados += 1
        if errores:
            # Todo o nada: no se guarda nada si alguna fila falla.
            raise CommandError("No se cargó nada. Revisa: " + ", ".join(errores))
        self.stdout.write(self.style.SUCCESS(f"{creados} ajustes creados."))

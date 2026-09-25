from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from permisos.models import Empleado
from permisos.zeus import obtener_cliente


class Command(BaseCommand):
    help = "Sincroniza empleados desde Zeus Reloj (solo lectura). Programarlo con cron o el Programador de tareas."

    def add_arguments(self, parser):
        parser.add_argument(
            "--desactivar-ausentes", action="store_true",
            help="Marca como inactivos los empleados que ya no aparecen en Zeus.",
        )

    @transaction.atomic
    def handle(self, *args, **opciones):
        User = get_user_model()
        ahora = timezone.now()
        registros = list(obtener_cliente().listar())
        if not registros:
            self.stderr.write("Zeus no devolvió empleados; no se cambió nada.")
            return

        creados = actualizados = 0
        for r in registros:
            datos = dict(
                nombre=r.nombre, cargo=r.cargo, area=r.area, seccion=r.seccion,
                email=r.email, activo=r.activo, horario_inicio=r.horario_inicio,
                horario_fin=r.horario_fin, sincronizado_en=ahora,
            )
            if r.fecha_ingreso:  # si Zeus no la trae, no se borra la que Gestión Humana haya puesto
                datos["fecha_ingreso"] = r.fecha_ingreso
            emp, nuevo = Empleado.objects.update_or_create(cedula=r.cedula, defaults=datos)
            creados += nuevo
            actualizados += not nuevo

            # Usuario del portal: el nombre de usuario es la identificación.
            # Sin contraseña: se define con "restablecer contraseña" o SSO.
            if emp.usuario_id is None:
                usuario, _ = User.objects.get_or_create(
                    username=r.cedula, defaults={"email": r.email, "first_name": r.nombre[:150]}
                )
                if not usuario.has_usable_password():
                    usuario.set_unusable_password()
                emp.usuario = usuario
                emp.save(update_fields=["usuario"])
            emp.usuario.is_active = r.activo
            emp.usuario.email = r.email or emp.usuario.email
            emp.usuario.save(update_fields=["is_active", "email"])

        # Segunda pasada: jefes (el jefe puede aparecer después en el archivo).
        por_cedula = {e.cedula: e for e in Empleado.objects.all()}
        sin_jefe = []
        for r in registros:
            emp = por_cedula[r.cedula]
            jefe = por_cedula.get(r.jefe_cedula) if r.jefe_cedula else None
            if r.jefe_cedula and jefe is None:
                sin_jefe.append(r.cedula)
            if emp.jefe_id != (jefe.pk if jefe else None):
                emp.jefe = jefe
                emp.save(update_fields=["jefe"])

        if opciones["desactivar_ausentes"]:
            vistos = {r.cedula for r in registros}
            ausentes = Empleado.objects.exclude(cedula__in=vistos).filter(activo=True)
            for emp in ausentes:
                emp.activo = False
                emp.save(update_fields=["activo"])
                if emp.usuario_id:
                    emp.usuario.is_active = False
                    emp.usuario.save(update_fields=["is_active"])

        self.stdout.write(self.style.SUCCESS(
            f"Empleados: {creados} nuevos, {actualizados} actualizados."
        ))
        if sin_jefe:
            self.stderr.write(f"Jefe no encontrado en Zeus para: {', '.join(sin_jefe)}")

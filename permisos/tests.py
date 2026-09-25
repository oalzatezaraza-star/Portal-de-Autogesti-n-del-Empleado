from datetime import date, time

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import services as svc
from .models import Empleado, SolicitudPermiso, TipoPermiso

User = get_user_model()
E = SolicitudPermiso.Estado


def crear_empleado(cedula, nombre, jefe=None):
    usuario = User.objects.create_user(cedula, f"{cedula}@club.test", "clave-segura-123")
    return Empleado.objects.create(
        cedula=cedula, nombre=nombre, email=usuario.email, jefe=jefe, usuario=usuario, area="Golf"
    )


class FlujoPermisoTests(TestCase):
    def setUp(self):
        self.jefe = crear_empleado("100", "Ana Jefa")
        self.emp = crear_empleado("200", "Luis Empleado", jefe=self.jefe)
        self.otro_jefe = crear_empleado("300", "Otro Jefe")
        self.gh = User.objects.create_user("gh", "gh@club.test", "clave-segura-123")
        self.gh.groups.add(Group.objects.get(name=settings.GRUPO_GESTION_HUMANA))
        self.porteria = User.objects.create_user("por", "p@club.test", "clave-segura-123")
        self.porteria.groups.add(Group.objects.get(name=settings.GRUPO_PORTERIA))
        self.tipo = TipoPermiso.objects.create(nombre="Diligencia personal")

    def radicar(self, **extra):
        datos = dict(
            tipo=self.tipo, fecha_inicio=timezone.localdate(), fecha_fin=timezone.localdate(),
            hora_salida=time(14, 0), hora_llegada=time(16, 0), motivo="Cita",
        )
        datos.update(extra)
        return svc.radicar(self.emp, self.emp.usuario, **datos)

    def test_flujo_completo_deja_trazabilidad(self):
        s = self.radicar()
        self.assertEqual(s.estado, E.PENDIENTE_JEFE)
        svc.aprobar_por_jefe(s.pk, self.jefe.usuario)
        svc.visto_bueno_gh(s.pk, self.gh, descontable=True)
        s.refresh_from_db()
        self.assertEqual(s.estado, E.AUTORIZADO)
        self.assertTrue(s.descontable)
        self.assertEqual(s.historial.count(), 3)
        self.assertIn(s, svc.autorizadas_hoy())

    def test_porteria_no_ve_lo_no_autorizado(self):
        s = self.radicar()
        self.assertNotIn(s, svc.autorizadas_hoy())
        self.assertFalse(svc.puede_ver(self.porteria, s))

    def test_solo_el_jefe_inmediato_aprueba(self):
        s = self.radicar()
        with self.assertRaises(svc.PermisoError):
            svc.aprobar_por_jefe(s.pk, self.otro_jefe.usuario)
        with self.assertRaises(svc.PermisoError):
            svc.aprobar_por_jefe(s.pk, self.gh)

    def test_no_se_salta_al_visto_bueno_sin_jefe(self):
        s = self.radicar()
        with self.assertRaises(svc.PermisoError):
            svc.visto_bueno_gh(s.pk, self.gh, descontable=False)

    def test_rechazo_exige_motivo(self):
        s = self.radicar()
        with self.assertRaises(svc.PermisoError):
            svc.rechazar_por_jefe(s.pk, self.jefe.usuario, "  ")
        svc.rechazar_por_jefe(s.pk, self.jefe.usuario, "Hay evento ese día")
        s.refresh_from_db()
        self.assertEqual(s.estado, E.RECHAZADO)

    def test_no_se_decide_dos_veces(self):
        s = self.radicar()
        svc.aprobar_por_jefe(s.pk, self.jefe.usuario)
        with self.assertRaises(svc.PermisoError):
            svc.aprobar_por_jefe(s.pk, self.jefe.usuario)

    def test_cancelar(self):
        s = self.radicar()
        svc.cancelar(s.pk, self.emp.usuario)
        s.refresh_from_db()
        self.assertEqual(s.estado, E.CANCELADO)

    def test_autorizado_solo_lo_cancela_gh(self):
        s = self.radicar()
        svc.aprobar_por_jefe(s.pk, self.jefe.usuario)
        svc.visto_bueno_gh(s.pk, self.gh, descontable=False)
        with self.assertRaises(svc.PermisoError):
            svc.cancelar(s.pk, self.emp.usuario)
        svc.cancelar(s.pk, self.gh)

    def test_empleado_sin_jefe_no_puede_radicar(self):
        sin_jefe = crear_empleado("400", "Sin Jefe")
        with self.assertRaises(svc.PermisoError):
            svc.radicar(
                sin_jefe, sin_jefe.usuario, tipo=self.tipo, fecha_inicio=date.today(),
                fecha_fin=date.today(), hora_salida=time(9), hora_llegada=None, motivo="x",
            )

    def test_soporte_obligatorio_segun_tipo(self):
        tipo = TipoPermiso.objects.create(nombre="Cita médica", requiere_soporte=True)
        with self.assertRaises(svc.PermisoError):
            self.radicar(tipo=tipo)

    def test_historial_es_inmutable(self):
        s = self.radicar()
        registro = s.historial.first()
        with self.assertRaises(ValueError):
            registro.save()


class VistasTests(TestCase):
    def setUp(self):
        self.jefe = crear_empleado("100", "Ana Jefa")
        self.emp = crear_empleado("200", "Luis Empleado", jefe=self.jefe)
        self.ajeno = crear_empleado("500", "Ajeno")
        self.tipo = TipoPermiso.objects.create(nombre="Diligencia personal")

    def test_requiere_login(self):
        r = self.client.get(reverse("permisos:mis_solicitudes"))
        self.assertEqual(r.status_code, 302)

    def test_empleado_radica_desde_el_formulario(self):
        self.client.login(username="200", password="clave-segura-123")
        hoy = timezone.localdate().isoformat()
        r = self.client.post(reverse("permisos:nueva"), {
            "tipo": self.tipo.pk, "fecha_inicio": hoy, "hora_salida": "14:00",
            "hora_llegada": "16:00", "motivo": "Cita",
        })
        self.assertEqual(r.status_code, 302)
        self.assertEqual(SolicitudPermiso.objects.count(), 1)

    def test_un_empleado_no_ve_solicitudes_ajenas(self):
        s = svc.radicar(
            self.emp, self.emp.usuario, tipo=self.tipo, fecha_inicio=date.today(),
            fecha_fin=date.today(), hora_salida=time(9), hora_llegada=None, motivo="x",
        )
        self.client.login(username="500", password="clave-segura-123")
        r = self.client.get(reverse("permisos:detalle", args=[s.pk]))
        self.assertEqual(r.status_code, 403)

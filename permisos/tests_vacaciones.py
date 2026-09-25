from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import calendario as cal
from . import services as svc
from . import vacaciones as vac
from .models import AjusteVacaciones, Empleado, SolicitudVacaciones

User = get_user_model()
E = SolicitudVacaciones.Estado

REGLAS = dict(
    VACACIONES_DIAS_POR_ANIO=15,
    VACACIONES_DIAS_HABILES=[0, 1, 2, 3, 4, 5],
    VACACIONES_ANTIGUEDAD_MINIMA_DIAS=360,
    VACACIONES_ANTELACION_DIAS=15,
    VACACIONES_MIN_DIAS_POR_SOLICITUD=6,
    VACACIONES_PERMITIR_ANTICIPO=False,
)


def crear_empleado(cedula, nombre, jefe=None, ingreso="hace_3_anios"):
    usuario = User.objects.create_user(cedula, f"{cedula}@club.test", "clave-segura-123")
    fecha = None if ingreso is None else (
        timezone.localdate() - timedelta(days=365 * 3) if ingreso == "hace_3_anios" else ingreso
    )
    return Empleado.objects.create(
        cedula=cedula, nombre=nombre, email=usuario.email, jefe=jefe,
        usuario=usuario, area="Golf", fecha_ingreso=fecha,
    )


def lunes_en(dias_minimos):
    d = timezone.localdate() + timedelta(days=dias_minimos)
    while d.weekday() != 0:
        d += timedelta(days=1)
    return d


@override_settings(**REGLAS)
class VacacionesTests(TestCase):
    def setUp(self):
        self.jefe = crear_empleado("100", "Ana Jefa")
        self.emp = crear_empleado("200", "Luis Empleado", jefe=self.jefe)
        self.otro = crear_empleado("300", "Otro Jefe")
        self.gh = User.objects.create_user("gh", "gh@club.test", "clave-segura-123")
        self.gh.groups.add(Group.objects.get(name=settings.GRUPO_GESTION_HUMANA))
        self.inicio = lunes_en(30)
        self.fin = self.inicio + timedelta(days=8)  # lunes a martes de la semana siguiente

    def pedir(self, empleado=None, inicio=None, fin=None):
        empleado = empleado or self.emp
        return vac.radicar(
            empleado, empleado.usuario,
            fecha_inicio=inicio or self.inicio, fecha_fin=fin or self.fin,
        )

    def test_flujo_completo_y_saldo(self):
        antes = vac.calcular_saldo(self.emp).disponible
        s = self.pedir()
        self.assertEqual(s.estado, E.PENDIENTE_JEFE)
        dias, reintegro = vac.calcular_periodo(self.inicio, self.fin)
        self.assertEqual(s.dias_habiles, dias)
        self.assertEqual(s.fecha_reintegro, reintegro)
        # En trámite ya descuenta del disponible
        self.assertEqual(vac.calcular_saldo(self.emp).disponible, antes - dias)
        vac.aprobar_por_jefe(s.pk, self.jefe.usuario)
        vac.autorizar_por_gh(s.pk, self.gh)
        s.refresh_from_db()
        self.assertEqual(s.estado, E.AUTORIZADA)
        self.assertEqual(s.historial.count(), 3)
        self.assertEqual(vac.calcular_saldo(self.emp).autorizados, Decimal(dias))

    def test_solo_el_jefe_inmediato_aprueba(self):
        s = self.pedir()
        with self.assertRaises(svc.PermisoError):
            vac.aprobar_por_jefe(s.pk, self.otro.usuario)
        with self.assertRaises(svc.PermisoError):
            vac.autorizar_por_gh(s.pk, self.gh)  # aún no pasó por el jefe

    def test_rechazo_libera_el_saldo(self):
        antes = vac.calcular_saldo(self.emp).disponible
        s = self.pedir()
        with self.assertRaises(svc.PermisoError):
            vac.rechazar_por_jefe(s.pk, self.jefe.usuario, "")
        vac.rechazar_por_jefe(s.pk, self.jefe.usuario, "Temporada alta")
        self.assertEqual(vac.calcular_saldo(self.emp).disponible, antes)

    def test_antelacion_minima(self):
        with self.assertRaises(svc.PermisoError):
            self.pedir(inicio=lunes_en(3), fin=lunes_en(3) + timedelta(days=8))

    def test_antiguedad_minima(self):
        nuevo = crear_empleado("400", "Recién llegado", jefe=self.jefe,
                               ingreso=timezone.localdate() - timedelta(days=100))
        with self.assertRaises(svc.PermisoError):
            self.pedir(empleado=nuevo)

    def test_sin_fecha_de_ingreso(self):
        sin = crear_empleado("500", "Sin fecha", jefe=self.jefe, ingreso=None)
        with self.assertRaises(svc.PermisoError):
            self.pedir(empleado=sin)

    def test_saldo_insuficiente(self):
        vac.ajustar_saldo(self.emp, self.gh, Decimal("-100"), "Disfrutados antes del portal")
        with self.assertRaises(svc.PermisoError):
            self.pedir()

    def test_minimo_por_solicitud_salvo_saldo_completo(self):
        corto = self.inicio + timedelta(days=1)  # lunes y martes: 1 o 2 días hábiles según festivos
        dias_corto, _ = vac.calcular_periodo(self.inicio, corto)
        with self.assertRaises(svc.PermisoError):
            self.pedir(fin=corto)
        # Si solo le quedan esos días de saldo, sí puede pedirlos
        saldo = vac.calcular_saldo(self.emp).disponible
        vac.ajustar_saldo(self.emp, self.gh, -(saldo - dias_corto), "Dejar pocos días")
        s = self.pedir(fin=corto)
        self.assertEqual(s.dias_habiles, dias_corto)

    def test_no_se_cruzan_solicitudes(self):
        self.pedir()
        with self.assertRaises(svc.PermisoError):
            self.pedir(inicio=self.inicio + timedelta(days=3), fin=self.fin + timedelta(days=10))

    def test_rango_solo_domingos_no_vale(self):
        domingo = self.inicio - timedelta(days=1)
        with self.assertRaises(svc.PermisoError):
            self.pedir(inicio=domingo, fin=domingo)

    def test_autorizada_solo_la_cancela_gh_y_antes_de_empezar(self):
        s = self.pedir()
        vac.aprobar_por_jefe(s.pk, self.jefe.usuario)
        vac.autorizar_por_gh(s.pk, self.gh)
        with self.assertRaises(svc.PermisoError):
            vac.cancelar(s.pk, self.emp.usuario)
        vac.cancelar(s.pk, self.gh)
        s.refresh_from_db()
        self.assertEqual(s.estado, E.CANCELADA)

    def test_gh_no_cancela_vacaciones_que_ya_empezaron(self):
        s = self.pedir()
        vac.aprobar_por_jefe(s.pk, self.jefe.usuario)
        vac.autorizar_por_gh(s.pk, self.gh)
        SolicitudVacaciones.objects.filter(pk=s.pk).update(fecha_inicio=timezone.localdate())
        with self.assertRaises(svc.PermisoError):
            vac.cancelar(s.pk, self.gh)

    def test_solo_gh_ajusta_saldos_y_no_hay_ajustes_de_cero(self):
        with self.assertRaises(svc.PermisoError):
            vac.ajustar_saldo(self.emp, self.jefe.usuario, Decimal("1"), "x")
        with self.assertRaises(svc.PermisoError):
            vac.ajustar_saldo(self.emp, self.gh, Decimal("0"), "x")

    def test_ajustes_son_inmutables(self):
        a = vac.ajustar_saldo(self.emp, self.gh, Decimal("-3"), "Disfrutados antes")
        with self.assertRaises(ValueError):
            a.save()
        with self.assertRaises(ValueError):
            a.delete()

    def test_coincidencias_del_equipo(self):
        otro_empleado = crear_empleado("600", "Compañero", jefe=self.jefe)
        mia = self.pedir()
        suya = self.pedir(empleado=otro_empleado)
        self.assertIn(suya, vac.coincidencias_equipo(mia))
        self.assertNotIn(mia, vac.coincidencias_equipo(mia))

    def test_al_autorizar_se_revalida_el_saldo(self):
        s = self.pedir()
        vac.aprobar_por_jefe(s.pk, self.jefe.usuario)
        vac.ajustar_saldo(self.emp, self.gh, Decimal("-100"), "Corrección de nómina")
        with self.assertRaises(svc.PermisoError):
            vac.autorizar_por_gh(s.pk, self.gh)
        s.refresh_from_db()
        self.assertEqual(s.estado, E.PENDIENTE_GH)


@override_settings(**REGLAS)
class VacacionesVistasTests(TestCase):
    def setUp(self):
        self.jefe = crear_empleado("100", "Ana Jefa")
        self.emp = crear_empleado("200", "Luis Empleado", jefe=self.jefe)
        self.ajeno = crear_empleado("500", "Ajeno")

    def test_empleado_pide_vacaciones_desde_el_formulario(self):
        self.client.login(username="200", password="clave-segura-123")
        inicio = lunes_en(30)
        r = self.client.post(reverse("permisos:vac_nueva"), {
            "fecha_inicio": inicio.isoformat(),
            "fecha_fin": (inicio + timedelta(days=8)).isoformat(),
        })
        self.assertEqual(r.status_code, 302)
        self.assertEqual(SolicitudVacaciones.objects.count(), 1)

    def test_no_se_ven_vacaciones_ajenas(self):
        inicio = lunes_en(30)
        s = vac.radicar(self.emp, self.emp.usuario, fecha_inicio=inicio,
                        fecha_fin=inicio + timedelta(days=8))
        self.client.login(username="500", password="clave-segura-123")
        r = self.client.get(reverse("permisos:vac_detalle", args=[s.pk]))
        self.assertEqual(r.status_code, 403)

    def test_saldos_solo_para_gestion_humana(self):
        self.client.login(username="200", password="clave-segura-123")
        r = self.client.get(reverse("permisos:vac_saldos"))
        self.assertEqual(r.status_code, 403)

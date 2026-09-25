from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from . import personal as per
from . import services as svc
from .models import Empleado, Turno

User = get_user_model()


def crear_empleado(cedula, nombre, jefe=None):
    usuario = User.objects.create_user(cedula, f"{cedula}@club.test", "clave-segura-123")
    return Empleado.objects.create(cedula=cedula, nombre=nombre, jefe=jefe, usuario=usuario, area="Golf")


class TurnosTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("adminpersonal", "a@club.test", "clave-segura-123")
        self.admin.groups.add(Group.objects.get(name=settings.GRUPO_ADMIN_PERSONAL))
        self.otro = User.objects.create_user("otro", "o@club.test", "clave-segura-123")
        self.emp = crear_empleado("900", "Camilo Pardo")

    def test_solo_admin_personal_crea_turnos(self):
        with self.assertRaises(svc.PermisoError):
            per.guardar_turno(self.otro, None, "Turno A", ["1", "2"], "", True)
        t = per.guardar_turno(self.admin, None, "Turno A", ["1", "2", "3", "4", "5"], "Domingo y lunes", True)
        self.assertEqual(t.dias, [1, 2, 3, 4, 5])
        self.assertEqual(t.dias_legibles(), "Martes, Miércoles, Jueves, Viernes, Sábado")

    def test_turno_necesita_dias(self):
        with self.assertRaises(svc.PermisoError):
            per.guardar_turno(self.admin, None, "Turno vacío", [], "", True)

    def test_editar_empleado_deja_auditoria_y_respeta_permisos(self):
        turno = per.guardar_turno(self.admin, None, "Turno B", ["2", "3", "4", "5", "6"], "Lunes y martes", True)
        with self.assertRaises(svc.PermisoError):
            per.actualizar_empleado(self.emp, self.otro, {"cargo": "Supervisor"})
        per.actualizar_empleado(self.emp, self.admin, {"cargo": "Supervisor", "turno": turno})
        self.emp.refresh_from_db()
        self.assertEqual(self.emp.cargo, "Supervisor")
        self.assertEqual(self.emp.turno_id, turno.pk)
        self.assertEqual(self.emp.cambios.count(), 2)  # cargo y turno
        self.assertEqual(self.emp.actualizado_por_id, self.admin.pk)

    def test_no_registra_cambio_si_el_valor_es_igual(self):
        per.actualizar_empleado(self.emp, self.admin, {"cargo": self.emp.cargo})
        self.assertEqual(self.emp.cambios.count(), 0)


class VistasPersonalTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("adminpersonal", "a@club.test", "clave-segura-123")
        self.admin.groups.add(Group.objects.get(name=settings.GRUPO_ADMIN_PERSONAL))
        self.emp = crear_empleado("900", "Camilo Pardo")

    def test_empleado_normal_no_entra_a_editar_personal(self):
        self.client.login(username="900", password="clave-segura-123")
        r = self.client.get(reverse("permisos:personal_lista"))
        self.assertEqual(r.status_code, 403)

    def test_admin_personal_edita_desde_el_formulario(self):
        self.client.login(username="adminpersonal", password="clave-segura-123")
        r = self.client.post(reverse("permisos:personal_editar", args=[self.emp.pk]), {
            "cargo": "Jardinero senior", "area": "Golf", "seccion": "Campo",
            "email": "camilo@club.test", "activo": "on",
        })
        self.assertEqual(r.status_code, 302)
        self.emp.refresh_from_db()
        self.assertEqual(self.emp.cargo, "Jardinero senior")

    def test_mi_horario_muestra_el_turno_del_empleado(self):
        t = Turno.objects.create(nombre="Turno A", dias=[1, 2, 3, 4, 5])
        self.emp.turno = t
        self.emp.save()
        self.client.login(username="900", password="clave-segura-123")
        r = self.client.get(reverse("permisos:mi_horario"))
        self.assertContains(r, "Turno A")

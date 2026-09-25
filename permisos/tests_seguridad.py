from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import IntentoAcceso

User = get_user_model()


@override_settings(ACCESO_MAX_INTENTOS=3, ACCESO_BLOQUEO_MINUTOS=15)
class LoginSeguroTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("900", "c@club.test", "clave-correcta-123")

    def test_registra_intentos_exitosos_y_fallidos(self):
        self.client.post(reverse("login"), {"username": "900", "password": "mala"})
        self.client.post(reverse("login"), {"username": "900", "password": "clave-correcta-123"})
        self.assertEqual(IntentoAcceso.objects.filter(exitoso=False).count(), 1)
        self.assertEqual(IntentoAcceso.objects.filter(exitoso=True).count(), 1)

    def test_bloquea_tras_varios_intentos_fallidos(self):
        for _ in range(3):
            self.client.post(reverse("login"), {"username": "900", "password": "mala"})
        r = self.client.post(reverse("login"), {"username": "900", "password": "clave-correcta-123"})
        self.assertContains(r, "bloqueó temporalmente")
        # Ni con la contraseña correcta entra mientras esté bloqueado.
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_el_bloqueo_es_por_usuario_no_global(self):
        for _ in range(3):
            self.client.post(reverse("login"), {"username": "900", "password": "mala"})
        User.objects.create_user("901", "d@club.test", "otra-clave-123")
        r = self.client.post(reverse("login"), {"username": "901", "password": "otra-clave-123"})
        self.assertIn("_auth_user_id", self.client.session)

    def test_login_exitoso_limpia_el_contador(self):
        self.client.post(reverse("login"), {"username": "900", "password": "mala"})
        self.client.post(reverse("login"), {"username": "900", "password": "mala"})
        self.client.post(reverse("login"), {"username": "900", "password": "clave-correcta-123"})
        self.assertIn("_auth_user_id", self.client.session)

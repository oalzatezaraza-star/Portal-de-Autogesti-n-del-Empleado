"""Inicio de sesión con bitácora y bloqueo temporal por intentos fallidos.

El bloqueo se guarda en el caché de Django (memoria del proceso por defecto).
En una instalación con varios procesos o servidores, configura CACHES con
Redis o Memcached para que el conteo se comparta entre todos.
"""
from django.conf import settings
from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.shortcuts import redirect
from django.utils import timezone

from .models import IntentoAcceso
from . import services as svc
from . import personal as per

ROLES_LOGIN = [
    ("empleado", "Empleado"),
    ("jefe", "Jefe inmediato"),
    ("gh", "Gestión Humana"),
    ("porteria", "Portería"),
    ("personal", "Administración de personal"),
]


def _ip(request):
    adelante = request.META.get("HTTP_X_FORWARDED_FOR")
    return adelante.split(",")[0].strip() if adelante else request.META.get("REMOTE_ADDR", "0.0.0.0")


def _clave(usuario, ip):
    return f"intentos-acceso:{usuario.lower()}:{ip}"


def bloqueado(usuario, ip):
    return cache.get(_clave(usuario, ip), 0) >= settings.ACCESO_MAX_INTENTOS


class LoginSeguroView(LoginView):
    template_name = "registration/login.html"
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["roles_login"] = ROLES_LOGIN
        ctx["rol_elegido"] = self.request.GET.get("rol", "empleado")
        return ctx

    def post(self, request, *args, **kwargs):
        usuario = request.POST.get("username", "").strip()
        ip = _ip(request)
        if usuario and bloqueado(usuario, ip):
            IntentoAcceso.objects.create(
                usuario_escrito=usuario, ip=ip, exitoso=False,
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
            )
            return self.render_to_response(self.get_context_data(
                form=self.get_form(),
                bloqueo_minutos=settings.ACCESO_BLOQUEO_MINUTOS,
            ))
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        usuario = form.get_user()
        ip = _ip(self.request)
        cache.delete(_clave(usuario.username, ip))
        IntentoAcceso.objects.create(
            usuario_escrito=usuario.username, ip=ip, exitoso=True,
            user_agent=self.request.META.get("HTTP_USER_AGENT", "")[:255],
        )
        return super().form_valid(form)

    def form_invalid(self, form):
        usuario = self.request.POST.get("username", "").strip()
        ip = _ip(self.request)
        if usuario:
            clave = _clave(usuario, ip)
            intentos = cache.get(clave, 0) + 1
            cache.set(clave, intentos, timeout=settings.ACCESO_BLOQUEO_MINUTOS * 60)
            IntentoAcceso.objects.create(
                usuario_escrito=usuario, ip=ip, exitoso=False,
                user_agent=self.request.META.get("HTTP_USER_AGENT", "")[:255],
            )
        return super().form_invalid(form)

    def get_success_url(self):
        """Si la persona marcó un rol en el login y sí lo tiene, la mandamos
        directo a esa vista; si no, cae a la página de inicio de siempre, que
        ya redirige según su rol real."""
        user = self.request.user
        pedido = self.request.POST.get("rol") or self.request.GET.get("rol")
        mapa = {
            "jefe": (svc.es_jefe(user), "permisos:bandeja"),
            "gh": (svc.es_gestion_humana(user), "permisos:bandeja"),
            "porteria": (svc.es_porteria(user), "permisos:porteria"),
            "personal": (per.es_admin_personal(user), "permisos:personal_lista"),
        }
        if pedido in mapa:
            tiene_el_rol, destino = mapa[pedido]
            if tiene_el_rol:
                from django.urls import reverse
                return reverse(destino)
        return super().get_success_url()

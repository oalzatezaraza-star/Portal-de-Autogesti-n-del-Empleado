from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from permisos.views_auth import LoginSeguroView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("ingresar/", LoginSeguroView.as_view(), name="login"),
    path("salir/", auth_views.LogoutView.as_view(), name="logout"),

    # Activar cuenta / recuperar contraseña (mismo flujo para las dos cosas:
    # sync_empleados crea el usuario sin contraseña utilizable, así que el
    # primer ingreso de cada persona es "olvidé mi contraseña").
    path("clave/olvide/", auth_views.PasswordResetView.as_view(
        template_name="registration/clave_solicitar.html",
        email_template_name="registration/clave_correo.txt",
        subject_template_name="registration/clave_asunto.txt",
    ), name="password_reset"),
    path("clave/enviada/", auth_views.PasswordResetDoneView.as_view(
        template_name="registration/clave_enviada.html",
    ), name="password_reset_done"),
    path("clave/nueva/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(
        template_name="registration/clave_nueva.html",
    ), name="password_reset_confirm"),
    path("clave/lista/", auth_views.PasswordResetCompleteView.as_view(
        template_name="registration/clave_lista.html",
    ), name="password_reset_complete"),

    path("", include("permisos.urls")),
]

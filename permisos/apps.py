from django.apps import AppConfig
from django.db.models.signals import post_migrate


def crear_grupos(sender, **kwargs):
    """Crea los grupos que dan los roles de Gestión Humana y Portería."""
    from django.conf import settings
    from django.contrib.auth.models import Group

    for nombre in (settings.GRUPO_GESTION_HUMANA, settings.GRUPO_PORTERIA, settings.GRUPO_ADMIN_PERSONAL):
        Group.objects.get_or_create(name=nombre)


class PermisosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "permisos"
    verbose_name = "Permisos"

    def ready(self):
        post_migrate.connect(crear_grupos, sender=self)

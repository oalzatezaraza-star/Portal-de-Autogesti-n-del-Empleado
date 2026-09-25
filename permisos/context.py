from . import personal as per
from . import services as svc


def roles(request):
    """Expone los roles del usuario a las plantillas para mostrar solo el menú que le sirve."""
    u = request.user
    if not u.is_authenticated:
        return {}
    return {
        "rol_gh": svc.es_gestion_humana(u),
        "rol_jefe": svc.es_jefe(u),
        "rol_porteria": svc.es_porteria(u),
        "rol_admin_personal": per.es_admin_personal(u),
    }

"""Edición de datos del empleado y de turnos, hecha por la persona encargada
(grupo «Administración de personal»). Todo cambio manual queda en CambioEmpleado.

Esto no reemplaza a Zeus como fuente de identidad: cada sincronización
(sync_empleados) puede volver a pisar cargo/área/sección si Zeus los trae. Lo
que Zeus no expone —el turno— nunca lo toca la sincronización.
"""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from django.utils import timezone

from .models import CambioEmpleado, Empleado, Turno
from .services import PermisoError

CAMPOS_EDITABLES = ["cargo", "area", "seccion", "email", "turno", "activo"]
ETIQUETAS = {
    "cargo": "Cargo", "area": "Departamento", "seccion": "Sección",
    "email": "Correo", "turno": "Turno", "activo": "Vínculo activo",
}

# Casilla del formulario -> nombre del grupo de Django que le da ese rol.
ROLES = {
    "rol_gestion_humana": settings.GRUPO_GESTION_HUMANA,
    "rol_porteria": settings.GRUPO_PORTERIA,
    "rol_admin_personal": settings.GRUPO_ADMIN_PERSONAL,
}


def es_admin_personal(user):
    return user.groups.filter(name=settings.GRUPO_ADMIN_PERSONAL).exists()


def roles_actuales(usuario_cuenta):
    """Para precargar las casillas del formulario de edición."""
    if usuario_cuenta is None:
        return {clave: False for clave in ROLES}
    nombres = set(usuario_cuenta.groups.values_list("name", flat=True))
    return {clave: grupo in nombres for clave, grupo in ROLES.items()}


def _aplicar_roles(usuario_cuenta, datos):
    """Deja al usuario únicamente en los grupos marcados en el formulario
    (no toca otros grupos que no sean de estos tres roles del portal)."""
    grupos_marcados = {grupo for clave, grupo in ROLES.items() if datos.get(clave)}
    grupos_del_portal = set(ROLES.values())
    actuales = set(usuario_cuenta.groups.filter(name__in=grupos_del_portal).values_list("name", flat=True))
    if grupos_marcados == actuales:
        return
    usuario_cuenta.groups.remove(*Group.objects.filter(name__in=grupos_del_portal - grupos_marcados))
    if grupos_marcados:
        usuario_cuenta.groups.add(*Group.objects.filter(name__in=grupos_marcados))


@transaction.atomic
def actualizar_empleado(empleado, usuario, datos):
    """`datos` trae los campos de CAMPOS_EDITABLES que cambiaron, más las
    casillas de rol y, si se llenó, una contraseña nueva."""
    if not es_admin_personal(usuario):
        raise PermisoError("Solo la persona encargada de personal puede editar estos datos.")

    for campo, valor in datos.items():
        if campo not in CAMPOS_EDITABLES:
            continue
        anterior = getattr(empleado, campo)
        if anterior == valor:
            continue
        CambioEmpleado.objects.create(
            empleado=empleado, usuario=usuario, campo=ETIQUETAS.get(campo, campo),
            valor_anterior=str(anterior) if anterior is not None else "",
            valor_nuevo=str(valor) if valor is not None else "",
        )
        setattr(empleado, campo, valor)

    empleado.actualizado_por = usuario
    empleado.actualizado_manualmente_en = timezone.now()
    empleado.save()

    if empleado.usuario_id:
        _aplicar_roles(empleado.usuario, datos)
        nueva_contrasena = datos.get("nueva_contrasena")
        if nueva_contrasena:
            empleado.usuario.set_password(nueva_contrasena)
            empleado.usuario.save(update_fields=["password"])
    return empleado


@transaction.atomic
def crear_empleado(usuario_actor, datos):
    """Alta de un empleado nuevo desde el propio portal: crea el registro
    del empleado y su usuario de acceso (usuario = identificación)."""
    if not es_admin_personal(usuario_actor):
        raise PermisoError("Solo la persona encargada de personal puede crear empleados.")

    User = get_user_model()
    cuenta = User(username=datos["cedula"], email=datos.get("email") or "",
                  first_name=datos["nombre"][:150])
    if datos.get("contrasena_inicial"):
        cuenta.set_password(datos["contrasena_inicial"])
    else:
        cuenta.set_unusable_password()
    cuenta.save()
    _aplicar_roles(cuenta, datos)

    empleado = Empleado.objects.create(
        cedula=datos["cedula"], nombre=datos["nombre"], cargo=datos.get("cargo", ""),
        area=datos.get("area", ""), seccion=datos.get("seccion", ""), email=datos.get("email", ""),
        jefe=datos.get("jefe"), turno=datos.get("turno"), fecha_ingreso=datos.get("fecha_ingreso"),
        usuario=cuenta, actualizado_por=usuario_actor, actualizado_manualmente_en=timezone.now(),
    )
    return empleado


def guardar_turno(usuario, turno_id, nombre, dias, descanso, activo):
    if not es_admin_personal(usuario):
        raise PermisoError("Solo la persona encargada de personal puede editar los turnos.")
    if not nombre.strip():
        raise PermisoError("El turno necesita un nombre.")
    if not dias:
        raise PermisoError("Elige al menos un día para el turno.")
    defaults = dict(nombre=nombre.strip(), dias=sorted(int(d) for d in dias),
                     descanso=descanso.strip(), activo=activo)
    if turno_id:
        Turno.objects.filter(pk=turno_id).update(**defaults)
        return Turno.objects.get(pk=turno_id)
    return Turno.objects.create(**defaults)

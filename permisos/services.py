"""Reglas del flujo Empleado → Jefe inmediato → Gestión Humana → Portería.

Toda la lógica de estados vive aquí (no en las vistas), para que se pueda
probar y para que el admin, una API o una app móvil reusen las mismas reglas.
"""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import Adjunto, HistorialSolicitud as H, SolicitudPermiso

E = SolicitudPermiso.Estado
A = H.Accion


class PermisoError(Exception):
    """Error de negocio con un mensaje apto para mostrar al usuario."""


# --- Roles --------------------------------------------------------------

def empleado_de(user):
    return getattr(user, "empleado", None)


def es_gestion_humana(user):
    return user.groups.filter(name=settings.GRUPO_GESTION_HUMANA).exists()


def es_porteria(user):
    return user.groups.filter(name=settings.GRUPO_PORTERIA).exists()


def es_jefe_de(user, empleado):
    yo = empleado_de(user)
    return yo is not None and empleado.jefe_id == yo.pk


def es_jefe(user):
    yo = empleado_de(user)
    return yo is not None and yo.subordinados.exists()


def puede_ver(user, solicitud):
    if solicitud.empleado.usuario_id == user.pk:
        return True
    if es_jefe_de(user, solicitud.empleado) or es_gestion_humana(user):
        return True
    return es_porteria(user) and solicitud.estado == E.AUTORIZADO


# --- Notificaciones -----------------------------------------------------

def _notificar(destinatarios, asunto, cuerpo):
    correos = sorted({d for d in destinatarios if d})
    if not correos:
        return
    transaction.on_commit(
        lambda: send_mail(asunto, cuerpo, settings.DEFAULT_FROM_EMAIL, correos, fail_silently=True)
    )


def _correos_gestion_humana():
    User = get_user_model()
    return User.objects.filter(
        groups__name=settings.GRUPO_GESTION_HUMANA, is_active=True
    ).values_list("email", flat=True)


# --- Operaciones --------------------------------------------------------

def _registrar(solicitud, usuario, accion, anterior, comentario=""):
    H.objects.create(
        solicitud=solicitud, usuario=usuario, accion=accion,
        estado_anterior=anterior, estado_nuevo=solicitud.estado, comentario=comentario,
    )


@transaction.atomic
def radicar(empleado, usuario, *, tipo, fecha_inicio, fecha_fin, hora_salida,
            hora_llegada, motivo, soporte=None):
    if not empleado.activo:
        raise PermisoError("El vínculo del empleado no está activo.")
    if empleado.jefe is None:
        raise PermisoError(
            "No tienes un jefe inmediato asignado. Pide a Gestión Humana que lo actualice en Zeus."
        )
    if tipo.requiere_soporte and soporte is None:
        raise PermisoError(f"El permiso «{tipo.nombre}» requiere un soporte adjunto.")

    solicitud = SolicitudPermiso(
        empleado=empleado, tipo=tipo, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin,
        hora_salida=hora_salida, hora_llegada=hora_llegada, motivo=motivo,
        estado=E.PENDIENTE_JEFE,
    )
    solicitud.full_clean()
    solicitud.save()
    if soporte is not None:
        Adjunto.objects.create(solicitud=solicitud, archivo=soporte)
    _registrar(solicitud, usuario, A.RADICADA, "")
    _notificar(
        [empleado.jefe.email],
        f"Permiso No. {solicitud.pk} pendiente de tu aprobación",
        f"{empleado.nombre} solicitó un permiso para el {solicitud.fecha_inicio:%d/%m/%Y}. "
        "Ingresa al portal para aprobarlo o rechazarlo.",
    )
    return solicitud


def _cambiar(pk, usuario, *, desde, hacia, accion, comentario="", verificar=None, **campos):
    """Cambio de estado atómico: bloquea la fila, valida y deja historial."""
    with transaction.atomic():
        solicitud = get_object_or_404(SolicitudPermiso.objects.select_for_update(), pk=pk)
        if solicitud.estado not in desde:
            raise PermisoError(
                f"La solicitud ya está «{solicitud.get_estado_display()}» y no admite esta acción."
            )
        if verificar:
            verificar(solicitud)
        anterior = solicitud.estado
        solicitud.estado = hacia
        for nombre, valor in campos.items():
            setattr(solicitud, nombre, valor)
        solicitud.save()
        _registrar(solicitud, usuario, accion, anterior, comentario)
    return solicitud


def _exigir_comentario(comentario):
    if not comentario.strip():
        raise PermisoError("Escribe el motivo del rechazo.")


def aprobar_por_jefe(pk, usuario, comentario=""):
    def verificar(s):
        if not es_jefe_de(usuario, s.empleado):
            raise PermisoError("Solo el jefe inmediato puede aprobar esta solicitud.")

    s = _cambiar(pk, usuario, desde={E.PENDIENTE_JEFE}, hacia=E.PENDIENTE_GH,
                 accion=A.APROBADA_JEFE, comentario=comentario, verificar=verificar)
    _notificar(
        _correos_gestion_humana(),
        f"Permiso No. {s.pk} pendiente de Gestión Humana",
        f"El jefe inmediato aprobó el permiso de {s.empleado.nombre}. Falta tu visto bueno.",
    )
    return s


def rechazar_por_jefe(pk, usuario, comentario):
    _exigir_comentario(comentario)

    def verificar(s):
        if not es_jefe_de(usuario, s.empleado):
            raise PermisoError("Solo el jefe inmediato puede rechazar esta solicitud.")

    s = _cambiar(pk, usuario, desde={E.PENDIENTE_JEFE}, hacia=E.RECHAZADO,
                 accion=A.RECHAZADA_JEFE, comentario=comentario, verificar=verificar)
    _notificar([s.empleado.email], f"Permiso No. {s.pk} rechazado", f"Motivo: {comentario}")
    return s


def visto_bueno_gh(pk, usuario, *, descontable, comentario=""):
    def verificar(s):
        if not es_gestion_humana(usuario):
            raise PermisoError("Solo Gestión Humana puede dar el visto bueno.")

    s = _cambiar(pk, usuario, desde={E.PENDIENTE_GH}, hacia=E.AUTORIZADO,
                 accion=A.AUTORIZADA_GH, comentario=comentario,
                 verificar=verificar, descontable=descontable)
    _notificar([s.empleado.email], f"Permiso No. {s.pk} autorizado",
               "Tu permiso quedó autorizado y Portería ya puede verlo.")
    return s


def rechazar_por_gh(pk, usuario, comentario):
    _exigir_comentario(comentario)

    def verificar(s):
        if not es_gestion_humana(usuario):
            raise PermisoError("Solo Gestión Humana puede rechazar en esta etapa.")

    s = _cambiar(pk, usuario, desde={E.PENDIENTE_GH}, hacia=E.RECHAZADO,
                 accion=A.RECHAZADA_GH, comentario=comentario, verificar=verificar)
    _notificar([s.empleado.email], f"Permiso No. {s.pk} rechazado", f"Motivo: {comentario}")
    return s


def cancelar(pk, usuario, comentario=""):
    """El empleado cancela mientras no esté autorizado; Gestión Humana, siempre."""
    def verificar(s):
        dueno = s.empleado.usuario_id == usuario.pk
        if s.estado == E.AUTORIZADO:
            if not es_gestion_humana(usuario):
                raise PermisoError("Un permiso autorizado solo lo cancela Gestión Humana.")
        elif not (dueno or es_gestion_humana(usuario)):
            raise PermisoError("Solo quien radicó la solicitud puede cancelarla.")

    return _cambiar(pk, usuario, desde={E.PENDIENTE_JEFE, E.PENDIENTE_GH, E.AUTORIZADO},
                    hacia=E.CANCELADO, accion=A.CANCELADA, comentario=comentario,
                    verificar=verificar)


# --- Consultas ----------------------------------------------------------

def autorizadas_hoy():
    """Lo que ve Portería: permisos autorizados que cubren la fecha de hoy."""
    hoy = timezone.localdate()
    return (
        SolicitudPermiso.objects.filter(
            estado=E.AUTORIZADO, fecha_inicio__lte=hoy, fecha_fin__gte=hoy
        )
        .select_related("empleado", "tipo")
        .order_by("hora_salida")
    )


def pendientes_del_jefe(user):
    yo = empleado_de(user)
    if yo is None:
        return SolicitudPermiso.objects.none()
    return SolicitudPermiso.objects.filter(
        estado=E.PENDIENTE_JEFE, empleado__jefe=yo
    ).select_related("empleado", "tipo")


def pendientes_de_gh():
    return SolicitudPermiso.objects.filter(estado=E.PENDIENTE_GH).select_related("empleado", "tipo")

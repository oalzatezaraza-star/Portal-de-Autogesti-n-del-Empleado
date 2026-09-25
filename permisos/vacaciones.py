"""Reglas del flujo de vacaciones: Empleado → Jefe inmediato → Gestión Humana → Registro.

Saldo = días causados (según la fecha de ingreso) + ajustes de Gestión Humana
        − días ya autorizados − días en trámite.

Los parámetros (días por año, días hábiles, antelación, etc.) están en settings.py
y deben confirmarse con Gestión Humana o el asesor laboral.
"""
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone

from . import calendario as cal
from .models import AjusteVacaciones, HistorialVacaciones as H, SolicitudVacaciones
from .services import (
    PermisoError, _correos_gestion_humana, _notificar, es_gestion_humana, es_jefe_de,
)

E = SolicitudVacaciones.Estado
A = H.Accion
EN_TRAMITE = (E.PENDIENTE_JEFE, E.PENDIENTE_GH)
ACTIVAS = (E.PENDIENTE_JEFE, E.PENDIENTE_GH, E.AUTORIZADA)


def _dias_semana():
    return set(settings.VACACIONES_DIAS_HABILES)


# --- Saldo --------------------------------------------------------------

@dataclass
class Saldo:
    sin_fecha_ingreso: bool
    causados: Decimal
    ajustes: Decimal
    autorizados: Decimal
    en_tramite: Decimal

    @property
    def disponible(self):
        return self.causados + self.ajustes - self.autorizados - self.en_tramite


def calcular_saldo(empleado, hasta=None, excluir_pk=None):
    hasta = hasta or timezone.localdate()
    if empleado.fecha_ingreso:
        causados = cal.dias_causados(empleado.fecha_ingreso, hasta, settings.VACACIONES_DIAS_POR_ANIO)
    else:
        causados = Decimal("0")
    ajustes = empleado.ajustes_vacaciones.aggregate(t=Sum("dias"))["t"] or Decimal("0")
    solicitudes = empleado.vacaciones.all()
    if excluir_pk:
        solicitudes = solicitudes.exclude(pk=excluir_pk)
    total = lambda estados: Decimal(  # noqa: E731
        solicitudes.filter(estado__in=estados).aggregate(t=Sum("dias_habiles"))["t"] or 0
    )
    return Saldo(
        sin_fecha_ingreso=empleado.fecha_ingreso is None,
        causados=causados, ajustes=ajustes,
        autorizados=total([E.AUTORIZADA]), en_tramite=total(EN_TRAMITE),
    )


def calcular_periodo(fecha_inicio, fecha_fin):
    """Días hábiles del período y fecha de reintegro, según los parámetros del Club."""
    dias = cal.contar_dias_habiles(fecha_inicio, fecha_fin, _dias_semana())
    return dias, cal.siguiente_dia_habil(fecha_fin, _dias_semana())


def _fmt(n):
    return f"{n:.2f}".rstrip("0").rstrip(".")


def _validar(empleado, inicio, fin, *, excluir_pk=None, exigir_antelacion=True):
    """Aplica las reglas y devuelve (días hábiles, fecha de reintegro)."""
    if not empleado.activo:
        raise PermisoError("El vínculo del empleado no está activo.")
    if empleado.fecha_ingreso is None:
        raise PermisoError(
            "Gestión Humana debe registrar tu fecha de ingreso antes de que puedas pedir vacaciones."
        )
    if fin < inicio:
        raise PermisoError("El último día no puede ser anterior al primero.")
    if exigir_antelacion:
        primero = timezone.localdate() + timedelta(days=settings.VACACIONES_ANTELACION_DIAS)
        if inicio < primero:
            raise PermisoError(
                f"Las vacaciones se piden con al menos {settings.VACACIONES_ANTELACION_DIAS} días de "
                f"anticipación. La primera fecha posible es el {primero:%d/%m/%Y}."
            )
    minimo_antig = settings.VACACIONES_ANTIGUEDAD_MINIMA_DIAS
    if minimo_antig and not cal.cumple_antiguedad(empleado.fecha_ingreso, inicio, minimo_antig):
        raise PermisoError("Aún no cumples el tiempo de servicio requerido para disfrutar vacaciones en esas fechas.")

    dias, reintegro = calcular_periodo(inicio, fin)
    if dias < 1:
        raise PermisoError("Ese rango no incluye ningún día hábil (solo domingos o festivos).")

    choque = SolicitudVacaciones.objects.filter(
        empleado=empleado, estado__in=ACTIVAS, fecha_inicio__lte=fin, fecha_fin__gte=inicio,
    )
    if excluir_pk:
        choque = choque.exclude(pk=excluir_pk)
    if choque.exists():
        raise PermisoError("Ya tienes otra solicitud de vacaciones que se cruza con esas fechas.")

    saldo = calcular_saldo(empleado, excluir_pk=excluir_pk)
    disponible = saldo.disponible
    if dias > disponible and not settings.VACACIONES_PERMITIR_ANTICIPO:
        raise PermisoError(
            f"Pides {dias} días hábiles y tu saldo disponible es de {_fmt(disponible)}."
        )
    minimo = settings.VACACIONES_MIN_DIAS_POR_SOLICITUD
    if dias < minimo and dias < int(disponible):
        raise PermisoError(
            f"Cada solicitud debe tener al menos {minimo} días hábiles, "
            "salvo que uses todo tu saldo disponible."
        )
    return dias, reintegro


def _registrar(solicitud, usuario, accion, anterior, comentario=""):
    H.objects.create(
        solicitud=solicitud, usuario=usuario, accion=accion,
        estado_anterior=anterior, estado_nuevo=solicitud.estado, comentario=comentario,
    )


# --- Operaciones --------------------------------------------------------

@transaction.atomic
def radicar(empleado, usuario, *, fecha_inicio, fecha_fin, observaciones=""):
    if empleado.jefe is None:
        raise PermisoError(
            "No tienes un jefe inmediato asignado. Pide a Gestión Humana que lo actualice en Zeus."
        )
    # Se bloquea al empleado para que dos solicitudes simultáneas no se salten el saldo.
    type(empleado).objects.select_for_update().get(pk=empleado.pk)
    dias, reintegro = _validar(empleado, fecha_inicio, fecha_fin)
    s = SolicitudVacaciones.objects.create(
        empleado=empleado, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin,
        fecha_reintegro=reintegro, dias_habiles=dias, observaciones=observaciones,
        estado=E.PENDIENTE_JEFE,
    )
    _registrar(s, usuario, A.RADICADA, "")
    _notificar(
        [empleado.jefe.email],
        f"Vacaciones No. {s.pk} pendientes de tu aprobación",
        f"{empleado.nombre} solicita vacaciones del {fecha_inicio:%d/%m/%Y} al {fecha_fin:%d/%m/%Y} "
        f"({dias} días hábiles). Ingresa al portal para decidir.",
    )
    return s


def _cambiar(pk, usuario, *, desde, hacia, accion, comentario="", verificar=None):
    with transaction.atomic():
        s = get_object_or_404(SolicitudVacaciones.objects.select_for_update(), pk=pk)
        if s.estado not in desde:
            raise PermisoError(
                f"La solicitud ya está «{s.get_estado_display()}» y no admite esta acción."
            )
        if verificar:
            verificar(s)
        anterior = s.estado
        s.estado = hacia
        s.save()
        _registrar(s, usuario, accion, anterior, comentario)
    return s


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
        f"Vacaciones No. {s.pk} pendientes de Gestión Humana",
        f"El jefe inmediato aprobó las vacaciones de {s.empleado.nombre}. Falta tu confirmación.",
    )
    return s


def rechazar_por_jefe(pk, usuario, comentario):
    _exigir_comentario(comentario)

    def verificar(s):
        if not es_jefe_de(usuario, s.empleado):
            raise PermisoError("Solo el jefe inmediato puede rechazar esta solicitud.")

    s = _cambiar(pk, usuario, desde={E.PENDIENTE_JEFE}, hacia=E.RECHAZADA,
                 accion=A.RECHAZADA_JEFE, comentario=comentario, verificar=verificar)
    _notificar([s.empleado.email], f"Vacaciones No. {s.pk} rechazadas", f"Motivo: {comentario}")
    return s


def autorizar_por_gh(pk, usuario, comentario=""):
    """Confirma y registra las vacaciones. Vuelve a validar saldo y cruces."""
    def verificar(s):
        if not es_gestion_humana(usuario):
            raise PermisoError("Solo Gestión Humana puede autorizar y registrar las vacaciones.")
        _validar(s.empleado, s.fecha_inicio, s.fecha_fin, excluir_pk=s.pk, exigir_antelacion=False)

    s = _cambiar(pk, usuario, desde={E.PENDIENTE_GH}, hacia=E.AUTORIZADA,
                 accion=A.AUTORIZADA_GH, comentario=comentario, verificar=verificar)
    _notificar(
        [s.empleado.email], f"Vacaciones No. {s.pk} autorizadas",
        f"Del {s.fecha_inicio:%d/%m/%Y} al {s.fecha_fin:%d/%m/%Y}. "
        f"Te reintegras el {s.fecha_reintegro:%d/%m/%Y}.",
    )
    return s


def rechazar_por_gh(pk, usuario, comentario):
    _exigir_comentario(comentario)

    def verificar(s):
        if not es_gestion_humana(usuario):
            raise PermisoError("Solo Gestión Humana puede rechazar en esta etapa.")

    s = _cambiar(pk, usuario, desde={E.PENDIENTE_GH}, hacia=E.RECHAZADA,
                 accion=A.RECHAZADA_GH, comentario=comentario, verificar=verificar)
    _notificar([s.empleado.email], f"Vacaciones No. {s.pk} rechazadas", f"Motivo: {comentario}")
    return s


def cancelar(pk, usuario, comentario=""):
    """El empleado cancela mientras esté en trámite. Una autorizada solo la cancela
    Gestión Humana y solo si aún no empiezan; si ya empezaron, se corrige con un ajuste."""
    def verificar(s):
        dueno = s.empleado.usuario_id == usuario.pk
        if s.estado == E.AUTORIZADA:
            if not es_gestion_humana(usuario):
                raise PermisoError("Unas vacaciones autorizadas solo las cancela Gestión Humana.")
            if s.fecha_inicio <= timezone.localdate():
                raise PermisoError(
                    "Las vacaciones ya empezaron. Para corregir el saldo, registra un ajuste."
                )
        elif not (dueno or es_gestion_humana(usuario)):
            raise PermisoError("Solo quien radicó la solicitud puede cancelarla.")

    return _cambiar(pk, usuario, desde={E.PENDIENTE_JEFE, E.PENDIENTE_GH, E.AUTORIZADA},
                    hacia=E.CANCELADA, accion=A.CANCELADA, comentario=comentario,
                    verificar=verificar)


def ajustar_saldo(empleado, usuario, dias, motivo):
    if not es_gestion_humana(usuario):
        raise PermisoError("Solo Gestión Humana puede ajustar saldos.")
    if not dias:
        raise PermisoError("El ajuste no puede ser de cero días.")
    if not motivo.strip():
        raise PermisoError("Escribe el motivo del ajuste.")
    return AjusteVacaciones.objects.create(
        empleado=empleado, dias=dias, motivo=motivo.strip(), creado_por=usuario
    )


# --- Consultas ----------------------------------------------------------

def puede_ver(user, s):
    return s.empleado.usuario_id == user.pk or es_jefe_de(user, s.empleado) or es_gestion_humana(user)


def pendientes_del_jefe(user):
    from .services import empleado_de
    yo = empleado_de(user)
    if yo is None:
        return SolicitudVacaciones.objects.none()
    return SolicitudVacaciones.objects.filter(
        estado=E.PENDIENTE_JEFE, empleado__jefe=yo
    ).select_related("empleado")


def pendientes_de_gh():
    return SolicitudVacaciones.objects.filter(estado=E.PENDIENTE_GH).select_related("empleado")


def coincidencias_equipo(s):
    """Otras personas del mismo jefe con vacaciones (o en trámite) que se cruzan con estas fechas.
    Sirve para decidir con la cobertura del equipo a la vista."""
    if s.empleado.jefe_id is None:
        return SolicitudVacaciones.objects.none()
    return (
        SolicitudVacaciones.objects.filter(
            estado__in=ACTIVAS, empleado__jefe_id=s.empleado.jefe_id,
            fecha_inicio__lte=s.fecha_fin, fecha_fin__gte=s.fecha_inicio,
        )
        .exclude(empleado_id=s.empleado_id)
        .select_related("empleado")
    )


def resumen_saldos():
    from .models import Empleado
    return [(e, calcular_saldo(e)) for e in Empleado.objects.filter(activo=True).select_related("jefe")]

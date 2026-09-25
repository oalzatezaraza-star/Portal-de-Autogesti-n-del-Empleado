import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import services as svc
from . import vacaciones as vac
from .forms import SolicitudForm
from .models import Adjunto, SolicitudPermiso

E = SolicitudPermiso.Estado


def _requerir_empleado(user):
    empleado = svc.empleado_de(user)
    if empleado is None:
        raise PermissionDenied("Tu usuario no está vinculado a un empleado de Zeus.")
    return empleado


@login_required
def inicio(request):
    """Cada rol aterriza en lo que más usa."""
    if svc.es_porteria(request.user) and not svc.es_gestion_humana(request.user):
        return redirect("permisos:porteria")
    if svc.es_gestion_humana(request.user) or svc.es_jefe(request.user):
        return redirect("permisos:bandeja")
    return redirect("permisos:mis_solicitudes")


@login_required
def mis_solicitudes(request):
    empleado = _requerir_empleado(request.user)
    solicitudes = empleado.solicitudes.select_related("tipo")
    return render(request, "permisos/mis_solicitudes.html", {"solicitudes": solicitudes})


@login_required
def nueva(request):
    empleado = _requerir_empleado(request.user)
    form = SolicitudForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        datos = form.cleaned_data
        try:
            solicitud = svc.radicar(
                empleado, request.user,
                tipo=datos["tipo"], fecha_inicio=datos["fecha_inicio"],
                fecha_fin=datos["fecha_fin"], hora_salida=datos["hora_salida"],
                hora_llegada=datos.get("hora_llegada"), motivo=datos["motivo"],
                soporte=datos.get("soporte"),
            )
        except (svc.PermisoError, ValidationError) as e:
            form.add_error(None, e.messages if isinstance(e, ValidationError) else str(e))
        else:
            messages.success(request, f"Solicitud No. {solicitud.pk} enviada a tu jefe inmediato.")
            return redirect("permisos:detalle", pk=solicitud.pk)
    return render(request, "permisos/nueva.html", {"form": form, "empleado": empleado})


@login_required
def detalle(request, pk):
    solicitud = get_object_or_404(
        SolicitudPermiso.objects.select_related("empleado", "tipo", "empleado__jefe"), pk=pk
    )
    if not svc.puede_ver(request.user, solicitud):
        raise PermissionDenied
    es_gh = svc.es_gestion_humana(request.user)
    dueno = solicitud.empleado.usuario_id == request.user.pk
    contexto = {
        "s": solicitud,
        "historial": solicitud.historial.select_related("usuario"),
        "adjuntos": solicitud.adjuntos.all(),
        "puede_decidir_jefe": solicitud.estado == E.PENDIENTE_JEFE
        and svc.es_jefe_de(request.user, solicitud.empleado),
        "puede_decidir_gh": solicitud.estado == E.PENDIENTE_GH and es_gh,
        "puede_cancelar": (dueno and solicitud.estado in (E.PENDIENTE_JEFE, E.PENDIENTE_GH))
        or (es_gh and solicitud.estado == E.AUTORIZADO),
    }
    return render(request, "permisos/detalle.html", contexto)


@login_required
@require_POST
def accion(request, pk):
    tipo = request.POST.get("accion", "")
    comentario = request.POST.get("comentario", "").strip()
    try:
        if tipo == "aprobar_jefe":
            svc.aprobar_por_jefe(pk, request.user, comentario)
            ok = "Aprobaste la solicitud. Pasó a Gestión Humana."
        elif tipo == "rechazar_jefe":
            svc.rechazar_por_jefe(pk, request.user, comentario)
            ok = "Rechazaste la solicitud."
        elif tipo == "visto_bueno":
            descontable = request.POST.get("descontable")
            if descontable not in ("si", "no"):
                raise svc.PermisoError("Indica si el tiempo es descontable.")
            svc.visto_bueno_gh(pk, request.user, descontable=descontable == "si",
                               comentario=comentario)
            ok = "Permiso autorizado. Portería ya puede verlo."
        elif tipo == "rechazar_gh":
            svc.rechazar_por_gh(pk, request.user, comentario)
            ok = "Rechazaste la solicitud."
        elif tipo == "cancelar":
            svc.cancelar(pk, request.user, comentario)
            ok = "Solicitud cancelada."
        else:
            raise svc.PermisoError("Acción no válida.")
    except svc.PermisoError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, ok)
    return redirect("permisos:detalle", pk=pk)


@login_required
def bandeja(request):
    es_gh = svc.es_gestion_humana(request.user)
    if not (es_gh or svc.es_jefe(request.user)):
        raise PermissionDenied
    return render(request, "permisos/bandeja.html", {
        "del_jefe": svc.pendientes_del_jefe(request.user),
        "de_gh": svc.pendientes_de_gh() if es_gh else [],
        "vac_jefe": vac.pendientes_del_jefe(request.user),
        "vac_gh": vac.pendientes_de_gh() if es_gh else [],
        "es_gh": es_gh,
    })


@login_required
def porteria(request):
    if not (svc.es_porteria(request.user) or svc.es_gestion_humana(request.user)):
        raise PermissionDenied
    q = request.GET.get("q", "").strip()
    lista = svc.autorizadas_hoy()
    if q:
        lista = lista.filter(Q(empleado__nombre__icontains=q) | Q(empleado__cedula__icontains=q))
    return render(request, "permisos/porteria.html", {"lista": lista, "q": q, "hoy": timezone.localdate()})


@login_required
def reporte(request):
    if not svc.es_gestion_humana(request.user):
        raise PermissionDenied
    filtros = Q()
    desde, hasta = request.GET.get("desde"), request.GET.get("hasta")
    area, estado = request.GET.get("area", "").strip(), request.GET.get("estado", "")
    if desde:
        filtros &= Q(fecha_inicio__gte=desde)
    if hasta:
        filtros &= Q(fecha_inicio__lte=hasta)
    if area:
        filtros &= Q(empleado__area__icontains=area)
    if estado in E.values:
        filtros &= Q(estado=estado)
    try:
        solicitudes = SolicitudPermiso.objects.filter(filtros).select_related("empleado", "tipo")
        solicitudes = list(solicitudes[:5000])
    except (ValidationError, ValueError):
        messages.error(request, "Revisa las fechas del filtro.")
        solicitudes = []

    if request.GET.get("formato") == "csv":
        respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
        respuesta["Content-Disposition"] = 'attachment; filename="permisos.csv"'
        respuesta.write("\ufeff")  # para que Excel respete las tildes
        w = csv.writer(respuesta)
        w.writerow(["No.", "Fecha", "Hasta", "Identificación", "Empleado", "Departamento",
                    "Sección", "Tipo", "Salida", "Llegada", "Descontable", "Estado"])
        for s in solicitudes:
            w.writerow([
                s.pk, s.fecha_inicio, s.fecha_fin, s.empleado.cedula, s.empleado.nombre,
                s.empleado.area, s.empleado.seccion, s.tipo.nombre,
                s.hora_salida.strftime("%H:%M"),
                s.hora_llegada.strftime("%H:%M") if s.hora_llegada else "",
                {True: "Sí", False: "No", None: ""}[s.descontable], s.get_estado_display(),
            ])
        return respuesta

    return render(request, "permisos/reporte.html", {
        "solicitudes": solicitudes, "estados": E.choices,
        "f": {"desde": desde or "", "hasta": hasta or "", "area": area, "estado": estado},
    })


@login_required
def imprimir_permiso(request, pk):
    """Versión lista para imprimir (o guardar como PDF) de un permiso ya
    decidido: sirve como el soporte físico que antes quedaba en papel."""
    solicitud = get_object_or_404(
        SolicitudPermiso.objects.select_related("empleado", "tipo", "empleado__jefe"), pk=pk
    )
    if not svc.puede_ver(request.user, solicitud):
        raise PermissionDenied
    return render(request, "permisos/imprimir.html", {
        "s": solicitud, "historial": solicitud.historial.select_related("usuario"),
    })


@login_required
def soporte(request, pk):
    """Los soportes (p. ej. incapacidades) solo los ve quien puede ver la solicitud."""
    adjunto = get_object_or_404(Adjunto.objects.select_related("solicitud__empleado"), pk=pk)
    if not svc.puede_ver(request.user, adjunto.solicitud):
        raise PermissionDenied
    try:
        return FileResponse(adjunto.archivo.open("rb"), as_attachment=True)
    except FileNotFoundError:
        raise Http404("El archivo ya no está disponible.")

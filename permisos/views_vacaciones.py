import csv

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import services as svc
from . import vacaciones as vac
from .forms import AjusteForm, VacacionesForm
from .models import SolicitudVacaciones
from .views import _requerir_empleado

E = SolicitudVacaciones.Estado


@login_required
def mis_vacaciones(request):
    empleado = _requerir_empleado(request.user)
    return render(request, "vacaciones/mis.html", {
        "empleado": empleado,
        "saldo": vac.calcular_saldo(empleado),
        "solicitudes": empleado.vacaciones.all(),
    })


@login_required
def nueva(request):
    empleado = _requerir_empleado(request.user)
    form = VacacionesForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            s = vac.radicar(
                empleado, request.user,
                fecha_inicio=form.cleaned_data["fecha_inicio"],
                fecha_fin=form.cleaned_data["fecha_fin"],
                observaciones=form.cleaned_data["observaciones"],
            )
        except svc.PermisoError as e:
            form.add_error(None, str(e))
        else:
            messages.success(
                request,
                f"Solicitud No. {s.pk} enviada a tu jefe inmediato: {s.dias_habiles} días hábiles, "
                f"te reintegras el {s.fecha_reintegro:%d/%m/%Y}.",
            )
            return redirect("permisos:vac_detalle", pk=s.pk)
    return render(request, "vacaciones/nueva.html", {
        "form": form, "empleado": empleado, "saldo": vac.calcular_saldo(empleado),
        "min_dias": settings.VACACIONES_MIN_DIAS_POR_SOLICITUD,
        "antelacion": settings.VACACIONES_ANTELACION_DIAS,
    })


@login_required
def detalle(request, pk):
    s = get_object_or_404(SolicitudVacaciones.objects.select_related("empleado", "empleado__jefe"), pk=pk)
    if not vac.puede_ver(request.user, s):
        raise PermissionDenied
    es_gh = svc.es_gestion_humana(request.user)
    dueno = s.empleado.usuario_id == request.user.pk
    es_su_jefe = svc.es_jefe_de(request.user, s.empleado)
    return render(request, "vacaciones/detalle.html", {
        "s": s,
        "historial": s.historial.select_related("usuario"),
        "saldo": vac.calcular_saldo(s.empleado, excluir_pk=s.pk),
        "coincidencias": vac.coincidencias_equipo(s) if (es_gh or es_su_jefe) else [],
        "puede_decidir_jefe": s.estado == E.PENDIENTE_JEFE and es_su_jefe,
        "puede_decidir_gh": s.estado == E.PENDIENTE_GH and es_gh,
        "puede_cancelar": (dueno and s.estado in (E.PENDIENTE_JEFE, E.PENDIENTE_GH))
        or (es_gh and s.estado == E.AUTORIZADA and s.fecha_inicio > timezone.localdate()),
    })


@login_required
@require_POST
def accion(request, pk):
    tipo = request.POST.get("accion", "")
    comentario = request.POST.get("comentario", "").strip()
    try:
        if tipo == "aprobar_jefe":
            vac.aprobar_por_jefe(pk, request.user, comentario)
            ok = "Aprobaste las vacaciones. Pasaron a Gestión Humana."
        elif tipo == "rechazar_jefe":
            vac.rechazar_por_jefe(pk, request.user, comentario)
            ok = "Rechazaste la solicitud."
        elif tipo == "autorizar":
            vac.autorizar_por_gh(pk, request.user, comentario)
            ok = "Vacaciones autorizadas y registradas."
        elif tipo == "rechazar_gh":
            vac.rechazar_por_gh(pk, request.user, comentario)
            ok = "Rechazaste la solicitud."
        elif tipo == "cancelar":
            vac.cancelar(pk, request.user, comentario)
            ok = "Solicitud cancelada."
        else:
            raise svc.PermisoError("Acción no válida.")
    except svc.PermisoError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, ok)
    return redirect("permisos:vac_detalle", pk=pk)


@login_required
def imprimir_vacaciones(request, pk):
    s = get_object_or_404(SolicitudVacaciones.objects.select_related("empleado", "empleado__jefe"), pk=pk)
    if not vac.puede_ver(request.user, s):
        raise PermissionDenied
    return render(request, "vacaciones/imprimir.html", {"s": s, "historial": s.historial.select_related("usuario")})


@login_required
def saldos(request):
    if not svc.es_gestion_humana(request.user):
        raise PermissionDenied
    form = AjusteForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            vac.ajustar_saldo(form.cleaned_data["empleado"], request.user,
                              form.cleaned_data["dias"], form.cleaned_data["motivo"])
        except svc.PermisoError as e:
            messages.error(request, str(e))
        else:
            messages.success(request, "Ajuste registrado.")
            return redirect("permisos:vac_saldos")
    return render(request, "vacaciones/saldos.html", {"filas": vac.resumen_saldos(), "form": form})


@login_required
def reporte(request):
    if not svc.es_gestion_humana(request.user):
        raise PermissionDenied
    filtros = Q()
    desde, hasta = request.GET.get("desde"), request.GET.get("hasta")
    area, estado = request.GET.get("area", "").strip(), request.GET.get("estado", "")
    if desde:
        filtros &= Q(fecha_fin__gte=desde)
    if hasta:
        filtros &= Q(fecha_inicio__lte=hasta)
    if area:
        filtros &= Q(empleado__area__icontains=area)
    if estado in E.values:
        filtros &= Q(estado=estado)
    try:
        lista = list(SolicitudVacaciones.objects.filter(filtros).select_related("empleado")[:5000])
    except (ValueError, ValidationError):  # fechas mal escritas en el filtro
        messages.error(request, "Revisa las fechas del filtro.")
        lista = []

    if request.GET.get("formato") == "csv":
        r = HttpResponse(content_type="text/csv; charset=utf-8")
        r["Content-Disposition"] = 'attachment; filename="vacaciones.csv"'
        r.write("\ufeff")
        w = csv.writer(r)
        w.writerow(["No.", "Identificación", "Empleado", "Departamento", "Primer día",
                    "Último día", "Reintegro", "Días hábiles", "Estado"])
        for s in lista:
            w.writerow([s.pk, s.empleado.cedula, s.empleado.nombre, s.empleado.area,
                        s.fecha_inicio, s.fecha_fin, s.fecha_reintegro, s.dias_habiles,
                        s.get_estado_display()])
        return r

    return render(request, "vacaciones/reporte.html", {
        "solicitudes": lista, "estados": E.choices,
        "f": {"desde": desde or "", "hasta": hasta or "", "area": area, "estado": estado},
    })

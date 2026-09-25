from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from . import personal as per
from . import services as svc
from .forms import EmpleadoCrearForm, EmpleadoEditForm, TurnoForm
from .models import Empleado, Turno


def _requerir_admin_personal(user):
    if not per.es_admin_personal(user):
        raise PermissionDenied


@login_required
def lista_empleados(request):
    _requerir_admin_personal(request.user)
    q = request.GET.get("q", "").strip()
    empleados = Empleado.objects.select_related("jefe", "turno")
    if q:
        empleados = empleados.filter(Q(nombre__icontains=q) | Q(cedula__icontains=q))
    return render(request, "personal/lista.html", {"empleados": empleados, "q": q})


@login_required
def nuevo_empleado(request):
    _requerir_admin_personal(request.user)
    form = EmpleadoCrearForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            empleado = per.crear_empleado(request.user, form.cleaned_data)
        except svc.PermisoError as e:
            form.add_error(None, str(e))
        else:
            messages.success(request, f"Se creó a {empleado.nombre} (usuario: {empleado.cedula}).")
            return redirect("permisos:personal_editar", pk=empleado.pk)
    return render(request, "personal/nuevo.html", {"form": form})


@login_required
def editar_empleado(request, pk):
    _requerir_admin_personal(request.user)
    empleado = get_object_or_404(Empleado, pk=pk)
    if request.method == "POST":
        form = EmpleadoEditForm(request.POST)
        if form.is_valid():
            try:
                per.actualizar_empleado(empleado, request.user, form.cleaned_data)
            except svc.PermisoError as e:
                messages.error(request, str(e))
            else:
                messages.success(request, f"Se actualizaron los datos de {empleado.nombre}.")
                return redirect("permisos:personal_lista")
    else:
        form = EmpleadoEditForm(initial={
            "cargo": empleado.cargo, "area": empleado.area, "seccion": empleado.seccion,
            "email": empleado.email, "turno": empleado.turno_id, "activo": empleado.activo,
            **per.roles_actuales(empleado.usuario),
        })
    return render(request, "personal/editar.html", {
        "form": form, "empleado": empleado, "cambios": empleado.cambios.select_related("usuario")[:20],
    })


@login_required
def turnos(request):
    _requerir_admin_personal(request.user)
    form = TurnoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            per.guardar_turno(request.user, d["turno_id"], d["nombre"], d["dias"], d["descanso"], d["activo"])
        except svc.PermisoError as e:
            messages.error(request, str(e))
        else:
            messages.success(request, "Turno guardado.")
            return redirect("permisos:personal_turnos")
    return render(request, "personal/turnos.html", {
        "form": form, "turnos": Turno.objects.all(), "empleados_sin_turno": Empleado.objects.filter(turno__isnull=True, activo=True),
    })


@login_required
def editar_turno(request, pk):
    _requerir_admin_personal(request.user)
    turno = get_object_or_404(Turno, pk=pk)
    form = TurnoForm(initial={
        "turno_id": turno.pk, "nombre": turno.nombre, "dias": [str(d) for d in turno.dias],
        "descanso": turno.descanso, "activo": turno.activo,
    })
    return render(request, "personal/turnos.html", {
        "form": form, "turnos": Turno.objects.all(), "editando": turno,
        "empleados_sin_turno": Empleado.objects.filter(turno__isnull=True, activo=True),
    })


@login_required
def mi_horario(request):
    empleado = getattr(request.user, "empleado", None)
    if empleado is None:
        raise PermissionDenied("Tu usuario no está vinculado a un empleado de Zeus.")
    equipo = []
    if empleado.subordinados.exists():
        equipo = empleado.subordinados.select_related("turno").filter(activo=True)
    return render(request, "personal/mi_horario.html", {"empleado": empleado, "equipo": equipo})

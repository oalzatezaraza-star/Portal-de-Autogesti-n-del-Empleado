from django.contrib import admin

from .models import (
    Adjunto, AjusteVacaciones, CambioEmpleado, Empleado, HistorialSolicitud, HistorialVacaciones,
    IntentoAcceso, SolicitudPermiso, SolicitudVacaciones, TipoPermiso, Turno,
)


@admin.register(Empleado)
class EmpleadoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "cedula", "cargo", "area", "jefe", "turno", "activo")
    list_filter = ("activo", "area", "turno")
    search_fields = ("nombre", "cedula")
    # Los datos que trae Zeus son de solo lectura aquí; los que edita la persona
    # encargada de personal (cargo, área, sección, email, turno, activo) se
    # cambian mejor desde «Empleados» en el menú, que sí deja auditoría.
    readonly_fields = ("cedula", "nombre", "jefe", "horario_inicio", "horario_fin",
                       "sincronizado_en", "actualizado_por", "actualizado_manualmente_en")
    # fecha_ingreso sí es editable: si Zeus no la expone, Gestión Humana la registra aquí.


@admin.register(Turno)
class TurnoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "dias_legibles", "descanso", "activo")
    list_filter = ("activo",)


@admin.register(CambioEmpleado)
class CambioEmpleadoAdmin(admin.ModelAdmin):
    list_display = ("empleado", "campo", "valor_anterior", "valor_nuevo", "usuario", "fecha")
    list_filter = ("campo",)
    search_fields = ("empleado__nombre", "empleado__cedula")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(IntentoAcceso)
class IntentoAccesoAdmin(admin.ModelAdmin):
    list_display = ("usuario_escrito", "ip", "exitoso", "fecha")
    list_filter = ("exitoso",)
    search_fields = ("usuario_escrito", "ip")
    readonly_fields = [f.name for f in IntentoAcceso._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(TipoPermiso)
class TipoPermisoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "requiere_soporte", "descontable_por_defecto", "activo")


class HistorialInline(admin.TabularInline):
    model = HistorialSolicitud
    extra = 0
    can_delete = False
    readonly_fields = ("usuario", "accion", "estado_anterior", "estado_nuevo", "comentario", "fecha")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(SolicitudPermiso)
class SolicitudAdmin(admin.ModelAdmin):
    list_display = ("id", "empleado", "tipo", "fecha_inicio", "estado", "descontable")
    list_filter = ("estado", "tipo")
    search_fields = ("empleado__nombre", "empleado__cedula")
    inlines = [HistorialInline]
    # El estado solo cambia por el flujo, nunca a mano.
    readonly_fields = ("estado", "descontable", "empleado", "creado_en", "actualizado_en")


admin.site.register(Adjunto)


class HistorialVacacionesInline(admin.TabularInline):
    model = HistorialVacaciones
    extra = 0
    can_delete = False
    readonly_fields = ("usuario", "accion", "estado_anterior", "estado_nuevo", "comentario", "fecha")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(SolicitudVacaciones)
class SolicitudVacacionesAdmin(admin.ModelAdmin):
    list_display = ("id", "empleado", "fecha_inicio", "fecha_fin", "dias_habiles", "estado")
    list_filter = ("estado",)
    search_fields = ("empleado__nombre", "empleado__cedula")
    inlines = [HistorialVacacionesInline]
    # El estado y los días solo cambian por el flujo, nunca a mano.
    readonly_fields = ("empleado", "fecha_inicio", "fecha_fin", "fecha_reintegro",
                       "dias_habiles", "estado", "creado_en", "actualizado_en")

    def has_add_permission(self, request):
        return False


@admin.register(AjusteVacaciones)
class AjusteVacacionesAdmin(admin.ModelAdmin):
    list_display = ("empleado", "dias", "motivo", "creado_por", "creado_en")
    search_fields = ("empleado__nombre", "empleado__cedula")
    readonly_fields = ("creado_por", "creado_en")

    def save_model(self, request, obj, form, change):
        if change:
            return  # los ajustes no se editan
        obj.creado_por = request.user
        super().save_model(request, obj, form, change)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

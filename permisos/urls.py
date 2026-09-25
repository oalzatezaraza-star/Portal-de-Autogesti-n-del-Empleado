from django.urls import path

from . import views, views_vacaciones as vv, views_personal as vp

app_name = "permisos"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("mis-solicitudes/", views.mis_solicitudes, name="mis_solicitudes"),
    path("solicitudes/nueva/", views.nueva, name="nueva"),
    path("solicitudes/<int:pk>/", views.detalle, name="detalle"),
    path("solicitudes/<int:pk>/accion/", views.accion, name="accion"),
    path("soportes/<int:pk>/", views.soporte, name="soporte"),
    path("bandeja/", views.bandeja, name="bandeja"),
    path("porteria/", views.porteria, name="porteria"),
    path("reportes/", views.reporte, name="reporte"),
    # Vacaciones
    path("vacaciones/", vv.mis_vacaciones, name="vac_mis"),
    path("vacaciones/nueva/", vv.nueva, name="vac_nueva"),
    path("vacaciones/saldos/", vv.saldos, name="vac_saldos"),
    path("vacaciones/reporte/", vv.reporte, name="vac_reporte"),
    path("vacaciones/<int:pk>/", vv.detalle, name="vac_detalle"),
    path("vacaciones/<int:pk>/accion/", vv.accion, name="vac_accion"),
    # Administración de personal
    path("personal/", vp.lista_empleados, name="personal_lista"),
    path("personal/nuevo/", vp.nuevo_empleado, name="personal_nuevo"),
    path("personal/<int:pk>/editar/", vp.editar_empleado, name="personal_editar"),
    path("personal/turnos/", vp.turnos, name="personal_turnos"),
    path("personal/turnos/<int:pk>/editar/", vp.editar_turno, name="personal_turno_editar"),
    path("mi-horario/", vp.mi_horario, name="mi_horario"),
    # Impresión de soportes
    path("solicitudes/<int:pk>/imprimir/", views.imprimir_permiso, name="imprimir_permiso"),
    path("vacaciones/<int:pk>/imprimir/", vv.imprimir_vacaciones, name="vac_imprimir"),
]

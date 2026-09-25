from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Empleado(models.Model):
    """Copia local de los datos básicos de Zeus Reloj.

    No se edita a mano: la llena el comando `sync_empleados`. Zeus es la fuente
    de verdad; aquí solo se guarda lo necesario para operar los flujos.
    """

    cedula = models.CharField("Identificación", max_length=20, unique=True)
    nombre = models.CharField("Nombre completo", max_length=150)
    cargo = models.CharField(max_length=120, blank=True)
    area = models.CharField("Departamento", max_length=120, blank=True)
    seccion = models.CharField("Sección", max_length=120, blank=True)
    email = models.EmailField(blank=True)
    jefe = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="subordinados", verbose_name="Jefe inmediato",
    )
    activo = models.BooleanField("Vínculo activo", default=True)
    horario_inicio = models.TimeField(null=True, blank=True)
    horario_fin = models.TimeField(null=True, blank=True)
    fecha_ingreso = models.DateField(
        "Fecha de ingreso", null=True, blank=True,
        help_text="Base para calcular las vacaciones causadas. Viene de Zeus si lo expone.",
    )
    turno = models.ForeignKey(
        "Turno", null=True, blank=True, on_delete=models.SET_NULL, related_name="empleados",
        help_text="Qué días de la semana trabaja. Lo asigna la persona encargada de horarios.",
    )
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="empleados_actualizados",
        help_text="Quién hizo la última edición manual (cargo, área, turno, etc.).",
    )
    actualizado_manualmente_en = models.DateTimeField(null=True, blank=True)
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="empleado",
    )
    sincronizado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.nombre} ({self.cedula})"


class TipoPermiso(models.Model):
    nombre = models.CharField(max_length=80, unique=True)
    requiere_soporte = models.BooleanField(default=False)
    descontable_por_defecto = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "tipo de permiso"
        verbose_name_plural = "tipos de permiso"

    def __str__(self):
        return self.nombre


class SolicitudPermiso(models.Model):
    """Equivale al formato físico de permisos. El número (No.) es el id."""

    class Estado(models.TextChoices):
        PENDIENTE_JEFE = "pendiente_jefe", "Pendiente de aprobación"
        PENDIENTE_GH = "pendiente_gh", "Aprobado por jefe inmediato (pendiente de Gestión Humana)"
        AUTORIZADO = "autorizado", "Autorizado"
        RECHAZADO = "rechazado", "Rechazado"
        CANCELADO = "cancelado", "Cancelado"

    empleado = models.ForeignKey(Empleado, on_delete=models.PROTECT, related_name="solicitudes")
    tipo = models.ForeignKey(TipoPermiso, on_delete=models.PROTECT)
    fecha_inicio = models.DateField("Fecha")
    fecha_fin = models.DateField("Hasta")
    hora_salida = models.TimeField("Hora de salida")
    hora_llegada = models.TimeField("Hora de llegada", null=True, blank=True)
    motivo = models.TextField("Razón del permiso")
    descontable = models.BooleanField("Tiempo descontable", null=True, blank=True)
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.PENDIENTE_JEFE)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]
        verbose_name = "solicitud de permiso"
        verbose_name_plural = "solicitudes de permiso"
        indexes = [
            models.Index(fields=["estado", "fecha_inicio"]),
        ]

    @property
    def numero(self):
        return self.pk

    def __str__(self):
        return f"No. {self.pk} - {self.empleado.nombre}"

    def clean(self):
        if self.fecha_inicio and self.fecha_fin and self.fecha_fin < self.fecha_inicio:
            raise ValidationError("La fecha final no puede ser anterior a la inicial.")
        if (
            self.fecha_inicio and self.fecha_fin and self.fecha_inicio == self.fecha_fin
            and self.hora_salida and self.hora_llegada
            and self.hora_llegada <= self.hora_salida
        ):
            raise ValidationError("La hora de llegada debe ser posterior a la de salida.")


def ruta_soporte(instance, nombre_archivo):
    return f"soportes/{instance.solicitud_id}/{nombre_archivo}"


class Adjunto(models.Model):
    solicitud = models.ForeignKey(SolicitudPermiso, on_delete=models.CASCADE, related_name="adjuntos")
    archivo = models.FileField(upload_to=ruta_soporte)
    subido_en = models.DateTimeField(auto_now_add=True)


class HistorialSolicitud(models.Model):
    """Registro inmutable de cada actuación sobre una solicitud."""

    class Accion(models.TextChoices):
        RADICADA = "radicada", "Radicó la solicitud"
        APROBADA_JEFE = "aprobada_jefe", "Aprobó (jefe inmediato)"
        RECHAZADA_JEFE = "rechazada_jefe", "Rechazó (jefe inmediato)"
        AUTORIZADA_GH = "autorizada_gh", "Dio visto bueno (Gestión Humana)"
        RECHAZADA_GH = "rechazada_gh", "Rechazó (Gestión Humana)"
        CANCELADA = "cancelada", "Canceló"

    solicitud = models.ForeignKey(SolicitudPermiso, on_delete=models.CASCADE, related_name="historial")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    accion = models.CharField(max_length=20, choices=Accion.choices)
    estado_anterior = models.CharField(max_length=20, blank=True)
    estado_nuevo = models.CharField(max_length=20)
    comentario = models.TextField(blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["fecha", "id"]
        verbose_name = "actuación"
        verbose_name_plural = "historial"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("El historial no se puede modificar.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("El historial no se puede borrar.")


# --------------------------------------------------------------------------
# Vacaciones
# --------------------------------------------------------------------------

class AjusteVacaciones(models.Model):
    """Libro de movimientos de saldo hechos por Gestión Humana.

    Positivo suma días (p. ej. días a favor); negativo resta (días ya disfrutados
    antes del portal, compensados en dinero, correcciones). Nunca se edita: si hay
    un error, se registra otro ajuste que lo compense.
    """

    empleado = models.ForeignKey(Empleado, on_delete=models.PROTECT, related_name="ajustes_vacaciones")
    dias = models.DecimalField("Días hábiles", max_digits=6, decimal_places=2)
    motivo = models.CharField(max_length=200)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]
        verbose_name = "ajuste de vacaciones"
        verbose_name_plural = "ajustes de vacaciones"

    def __str__(self):
        return f"{self.empleado.nombre}: {self.dias:+} días"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("Los ajustes no se pueden modificar; registra otro que lo compense.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Los ajustes no se pueden borrar; registra otro que lo compense.")


class SolicitudVacaciones(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE_JEFE = "pendiente_jefe", "Pendiente de aprobación"
        PENDIENTE_GH = "pendiente_gh", "Aprobada por jefe inmediato (pendiente de Gestión Humana)"
        AUTORIZADA = "autorizada", "Autorizada"
        RECHAZADA = "rechazada", "Rechazada"
        CANCELADA = "cancelada", "Cancelada"

    empleado = models.ForeignKey(Empleado, on_delete=models.PROTECT, related_name="vacaciones")
    fecha_inicio = models.DateField("Primer día de vacaciones")
    fecha_fin = models.DateField("Último día de vacaciones")
    fecha_reintegro = models.DateField("Fecha de reintegro")
    dias_habiles = models.PositiveSmallIntegerField("Días hábiles")
    observaciones = models.TextField(blank=True)
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.PENDIENTE_JEFE)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]
        verbose_name = "solicitud de vacaciones"
        verbose_name_plural = "solicitudes de vacaciones"
        indexes = [models.Index(fields=["estado", "fecha_inicio"])]

    def __str__(self):
        return f"Vacaciones No. {self.pk} - {self.empleado.nombre}"


class HistorialVacaciones(models.Model):
    """Registro inmutable de cada actuación sobre una solicitud de vacaciones."""

    class Accion(models.TextChoices):
        RADICADA = "radicada", "Radicó la solicitud"
        APROBADA_JEFE = "aprobada_jefe", "Aprobó (jefe inmediato)"
        RECHAZADA_JEFE = "rechazada_jefe", "Rechazó (jefe inmediato)"
        AUTORIZADA_GH = "autorizada_gh", "Autorizó y registró (Gestión Humana)"
        RECHAZADA_GH = "rechazada_gh", "Rechazó (Gestión Humana)"
        CANCELADA = "cancelada", "Canceló"

    solicitud = models.ForeignKey(SolicitudVacaciones, on_delete=models.CASCADE, related_name="historial")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    accion = models.CharField(max_length=20, choices=Accion.choices)
    estado_anterior = models.CharField(max_length=20, blank=True)
    estado_nuevo = models.CharField(max_length=20)
    comentario = models.TextField(blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["fecha", "id"]
        verbose_name = "actuación de vacaciones"
        verbose_name_plural = "historial de vacaciones"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("El historial no se puede modificar.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("El historial no se puede borrar.")


# --------------------------------------------------------------------------
# Turnos (dos horarios del Club: p. ej. martes a sábado, o miércoles a domingo)
# --------------------------------------------------------------------------

DIAS_SEMANA = [
    (0, "Lunes"), (1, "Martes"), (2, "Miércoles"), (3, "Jueves"),
    (4, "Viernes"), (5, "Sábado"), (6, "Domingo"),
]


class Turno(models.Model):
    """Un turno define qué días de la semana se trabaja (p. ej. Turno A: martes
    a sábado). Lo administra la persona encargada de personal y puede cambiar
    con el tiempo; los empleados solo ven a qué turno están asignados."""

    nombre = models.CharField(max_length=60, unique=True)
    dias = models.JSONField(
        "Días que trabaja",
        help_text="Números de día: 0=lunes … 6=domingo.",
        default=list,
    )
    descanso = models.CharField(
        "Día(s) de descanso", max_length=120, blank=True,
        help_text="Texto libre, por ejemplo «Domingo y lunes».",
    )
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

    def dias_legibles(self):
        nombres = dict(DIAS_SEMANA)
        return ", ".join(nombres[d] for d in sorted(self.dias) if d in nombres)


# --------------------------------------------------------------------------
# Auditoría de cambios sobre los datos del empleado (cargo, área, turno, etc.)
# --------------------------------------------------------------------------

class CambioEmpleado(models.Model):
    """Registro inmutable de cada edición manual sobre un empleado: quién,
    qué campo, de qué valor a qué valor y cuándo. No sustituye a Zeus como
    fuente de verdad; solo dice qué se tocó desde el portal."""

    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name="cambios")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    campo = models.CharField(max_length=60)
    valor_anterior = models.CharField(max_length=200, blank=True)
    valor_nuevo = models.CharField(max_length=200, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "cambio sobre un empleado"
        verbose_name_plural = "cambios sobre empleados"

    def __str__(self):
        return f"{self.empleado.nombre}: {self.campo} → {self.valor_nuevo}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("El historial de cambios no se puede modificar.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("El historial de cambios no se puede borrar.")


# --------------------------------------------------------------------------
# Seguridad: bitácora de intentos de acceso
# --------------------------------------------------------------------------

class IntentoAcceso(models.Model):
    """Bitácora de cada intento de inicio de sesión, exitoso o no. Sirve para
    detectar intentos de adivinar contraseñas y para el bloqueo temporal."""

    usuario_escrito = models.CharField("Usuario ingresado", max_length=150)
    ip = models.GenericIPAddressField()
    exitoso = models.BooleanField(default=False)
    user_agent = models.CharField(max_length=255, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha"]
        verbose_name = "intento de acceso"
        verbose_name_plural = "intentos de acceso"
        indexes = [models.Index(fields=["usuario_escrito", "ip", "fecha"])]

    def __str__(self):
        return f"{self.usuario_escrito} desde {self.ip} · {'OK' if self.exitoso else 'fallido'}"

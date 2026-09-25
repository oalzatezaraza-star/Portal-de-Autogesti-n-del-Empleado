from django import forms
from django.utils import timezone

from .models import SolicitudPermiso, TipoPermiso


class SolicitudForm(forms.ModelForm):
    soporte = forms.FileField(label="Soporte (si aplica)", required=False)

    class Meta:
        model = SolicitudPermiso
        fields = ["tipo", "fecha_inicio", "fecha_fin", "hora_salida", "hora_llegada", "motivo"]
        widgets = {
            "fecha_inicio": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "fecha_fin": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "hora_salida": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "hora_llegada": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "motivo": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {"fecha_fin": "Hasta (si dura más de un día)"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tipo"].queryset = TipoPermiso.objects.filter(activo=True)
        self.fields["fecha_fin"].required = False
        self.fields["hora_llegada"].required = False
        self.fields["fecha_inicio"].initial = timezone.localdate()

    def clean(self):
        datos = super().clean()
        if datos.get("fecha_inicio") and not datos.get("fecha_fin"):
            datos["fecha_fin"] = datos["fecha_inicio"]
        tipo = datos.get("tipo")
        if tipo and tipo.requiere_soporte and not datos.get("soporte"):
            self.add_error("soporte", f"El permiso «{tipo.nombre}» requiere un soporte.")
        return datos


class VacacionesForm(forms.Form):
    fecha_inicio = forms.DateField(
        label="Primer día de vacaciones",
        widget=forms.DateInput(attrs={"type": "date", "id": "vi", "class": "cal-input-real"}, format="%Y-%m-%d"),
    )
    fecha_fin = forms.DateField(
        label="Último día de vacaciones",
        widget=forms.DateInput(attrs={"type": "date", "id": "vf", "class": "cal-input-real"}, format="%Y-%m-%d"),
    )
    observaciones = forms.CharField(
        label="Observaciones (opcional)", required=False, widget=forms.Textarea(attrs={"rows": 3})
    )

    def clean(self):
        datos = super().clean()
        if datos.get("fecha_inicio") and datos.get("fecha_fin") and datos["fecha_fin"] < datos["fecha_inicio"]:
            self.add_error("fecha_fin", "El último día no puede ser anterior al primero.")
        return datos


class AjusteForm(forms.Form):
    empleado = forms.ModelChoiceField(queryset=None, label="Empleado")
    dias = forms.DecimalField(
        label="Días hábiles", max_digits=6, decimal_places=2,
        help_text="Positivo suma; negativo resta (por ejemplo, días ya disfrutados antes del portal).",
    )
    motivo = forms.CharField(label="Motivo", max_length=200)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import Empleado
        self.fields["empleado"].queryset = Empleado.objects.filter(activo=True)


class RolesAccesoMixin(forms.Form):
    """Casillas para asignar los roles especiales del portal (grupos de
    Django) sin tener que entrar al admin. Un empleado sin ninguna marcada
    es un empleado normal."""

    rol_gestion_humana = forms.BooleanField(label="Gestión Humana", required=False)
    rol_porteria = forms.BooleanField(label="Portería", required=False)
    rol_admin_personal = forms.BooleanField(label="Administración de personal", required=False)


class EmpleadoEditForm(RolesAccesoMixin):
    """Solo los campos que la persona encargada de personal puede tocar.
    Cédula, nombre y jefe siguen viniendo de Zeus (o de «Nuevo empleado»)."""

    cargo = forms.CharField(max_length=120, required=False)
    area = forms.CharField(label="Departamento", max_length=120, required=False)
    seccion = forms.CharField(label="Sección", max_length=120, required=False)
    email = forms.EmailField(required=False)
    turno = forms.ModelChoiceField(queryset=None, required=False, empty_label="Sin turno asignado")
    activo = forms.BooleanField(label="Vínculo activo", required=False)
    nueva_contrasena = forms.CharField(
        label="Poner una contraseña nueva", required=False, widget=forms.PasswordInput,
        help_text="Déjalo en blanco si no quieres cambiarla.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import Turno
        self.fields["turno"].queryset = Turno.objects.filter(activo=True)
        # Las casillas de rol van después de "activo" y antes de la contraseña.
        orden = ["cargo", "area", "seccion", "email", "turno", "activo",
                 "rol_gestion_humana", "rol_porteria", "rol_admin_personal", "nueva_contrasena"]
        self.order_fields(orden)


class EmpleadoCrearForm(RolesAccesoMixin):
    """Alta de un empleado nuevo directamente desde el portal, sin tener que
    tocar el archivo de Zeus ni el admin de Django. Crea el registro del
    empleado y, si se marca algún rol o se pone contraseña, también su
    usuario de acceso (el nombre de usuario es la identificación)."""

    cedula = forms.CharField(label="Identificación", max_length=20)
    nombre = forms.CharField(label="Nombre completo", max_length=150)
    cargo = forms.CharField(max_length=120, required=False)
    area = forms.CharField(label="Departamento", max_length=120, required=False)
    seccion = forms.CharField(label="Sección", max_length=120, required=False)
    email = forms.EmailField(required=False)
    jefe = forms.ModelChoiceField(
        queryset=None, required=False, empty_label="Sin jefe inmediato", label="Jefe inmediato",
    )
    turno = forms.ModelChoiceField(queryset=None, required=False, empty_label="Sin turno asignado")
    fecha_ingreso = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        help_text="Base para calcular las vacaciones causadas.",
    )
    contrasena_inicial = forms.CharField(
        label="Contraseña inicial", required=False, widget=forms.PasswordInput,
        help_text="Si la dejas en blanco, la persona deberá usar «¿Olvidaste tu contraseña?» "
                   "en el login (necesita tener un correo válido arriba).",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import Empleado, Turno
        self.fields["jefe"].queryset = Empleado.objects.filter(activo=True).order_by("nombre")
        self.fields["turno"].queryset = Turno.objects.filter(activo=True)
        self.order_fields([
            "cedula", "nombre", "cargo", "area", "seccion", "email", "jefe", "turno",
            "fecha_ingreso", "rol_gestion_humana", "rol_porteria", "rol_admin_personal",
            "contrasena_inicial",
        ])

    def clean_cedula(self):
        from django.contrib.auth import get_user_model
        from .models import Empleado
        cedula = self.cleaned_data["cedula"].strip()
        if Empleado.objects.filter(cedula=cedula).exists():
            raise forms.ValidationError("Ya existe un empleado con esa identificación.")
        if get_user_model().objects.filter(username=cedula).exists():
            raise forms.ValidationError(
                "Ya existe un usuario con ese nombre de usuario (se usa la identificación)."
            )
        return cedula


class TurnoForm(forms.Form):
    turno_id = forms.IntegerField(required=False, widget=forms.HiddenInput)
    nombre = forms.CharField(max_length=60)
    dias = forms.MultipleChoiceField(
        label="Días que trabaja", widget=forms.CheckboxSelectMultiple, choices=[],
    )
    descanso = forms.CharField(label="Día(s) de descanso (texto libre)", max_length=120, required=False)
    activo = forms.BooleanField(required=False, initial=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import DIAS_SEMANA
        self.fields["dias"].choices = [(str(n), nom) for n, nom in DIAS_SEMANA]

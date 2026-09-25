"""Configuración del Portal de Autogestión del Empleado.

Todo lo sensible se lee de variables de entorno. Sin variables, usa SQLite y
modo desarrollo, para poder probar el flujo en local.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env(nombre, defecto=""):
    return os.environ.get(nombre, defecto)


SECRET_KEY = env("DJANGO_SECRET_KEY", "cambiar-esto-en-produccion")
DEBUG = env("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = [h for h in env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "permisos.apps.PermisosConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "permisos.middleware.CabecerasSeguridadMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "permisos.context.roles",
            ],
        },
    },
]

if env("POSTGRES_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("POSTGRES_DB"),
            "USER": env("POSTGRES_USER"),
            "PASSWORD": env("POSTGRES_PASSWORD"),
            "HOST": env("POSTGRES_HOST", "localhost"),
            "PORT": env("POSTGRES_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-co"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "media/"
MEDIA_ROOT = Path(env("MEDIA_ROOT", str(BASE_DIR / "media")))
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "permisos:inicio"
LOGOUT_REDIRECT_URL = "login"

# Correo (notificaciones). En desarrollo se imprime en consola.
if env("EMAIL_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = env("EMAIL_HOST")
    EMAIL_PORT = int(env("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = env("EMAIL_HOST_USER")
    EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
    EMAIL_USE_TLS = True
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "portal@example.com")

# Zeus Reloj: "csv" (exportación periódica) o "sql" (consulta de solo lectura).
ZEUS_BACKEND = env("ZEUS_BACKEND", "csv")
ZEUS_CSV_PATH = env("ZEUS_CSV_PATH", str(BASE_DIR / "zeus_empleados.csv"))
ZEUS_ODBC_CONNECTION = env("ZEUS_ODBC_CONNECTION")  # cadena de conexión ODBC
ZEUS_SQL_QUERY = env("ZEUS_SQL_QUERY")  # ver permisos/zeus.py

# Nombres de los grupos que dan los roles especiales.
GRUPO_GESTION_HUMANA = "Gestión Humana"
GRUPO_PORTERIA = "Portería"
GRUPO_ADMIN_PERSONAL = "Administración de personal"  # edita cargo, área, turno de los empleados

# --- Seguridad --------------------------------------------------------
# Pensado para una instalación de un solo servidor detrás de HTTPS. En una
# instalación con varios procesos/servidores, cambia el caché (más abajo)
# a Redis o Memcached para que el bloqueo de intentos sea compartido.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 8          # 8 horas de sesión
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_FAILURE_VIEW = "permisos.errores.csrf_fallo"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
PASSWORD_RESET_TIMEOUT = 60 * 60 * 24     # el enlace para crear contraseña dura 1 día

# Intentos fallidos de inicio de sesión antes de bloquear temporalmente
# (por usuario + dirección IP). Ver permisos/views_auth.py.
ACCESO_MAX_INTENTOS = 5
ACCESO_BLOQUEO_MINUTOS = 15

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = env("DJANGO_SSL_REDIRECT", "1") == "1"
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# --- Reglas de vacaciones -------------------------------------------------
# IMPORTANTE: son valores de partida. Confirmarlos con Gestión Humana y el
# asesor laboral del Club antes de usar el módulo en producción.
VACACIONES_DIAS_POR_ANIO = 15            # días hábiles por cada año de servicio
VACACIONES_DIAS_HABILES = [0, 1, 2, 3, 4, 5]  # 0=lunes … 6=domingo. Aquí: lunes a sábado
VACACIONES_ANTIGUEDAD_MINIMA_DIAS = 360  # días laborados antes del primer disfrute (0 = sin límite)
VACACIONES_ANTELACION_DIAS = 15          # aviso mínimo entre la solicitud y el primer día
VACACIONES_MIN_DIAS_POR_SOLICITUD = 6    # salvo que use todo su saldo entero
VACACIONES_PERMITIR_ANTICIPO = False     # ¿puede pedir más días de los causados?

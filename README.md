# Portal de Autogestión del Empleado: permisos, vacaciones, personal y seguridad

Digitaliza el **Formato de Permisos** del Club. Flujo:
Empleado → Jefe inmediato → Gestión Humana → Portería.

Cada campo del formato de papel tiene su equivalente: el **No.** es el id de la
solicitud (automático), nombre/departamento/sección vienen de Zeus, las firmas
son aprobaciones con usuario, fecha y hora, y «tiempo descontable» lo marca
Gestión Humana al dar el visto bueno.

## Seguridad

Pensado para una empresa donde el acceso debe quedar controlado y auditado:

- **Bitácora de accesos** (`IntentoAcceso`): cada intento de inicio de sesión, exitoso o no, con usuario, IP y fecha. Visible en el administrador.
- **Bloqueo temporal:** tras `ACCESO_MAX_INTENTOS` (5 por defecto) intentos fallidos del mismo usuario desde la misma IP, se bloquea por `ACCESO_BLOQUEO_MINUTOS` (15 por defecto). El contador vive en el caché de Django (`permisos/views_auth.py`); en una instalación con varios procesos o servidores, cambia `CACHES` a Redis o Memcached para que el bloqueo se comparta entre todos.
- **Contraseñas propias, nunca puestas por un administrador:** `sync_empleados` crea cada usuario sin contraseña utilizable. La persona activa su cuenta con «¿Olvidaste tu contraseña?», que le llega por correo (enlace válido 24 horas). Es el mismo flujo para activar la cuenta la primera vez y para recuperarla después.
- **Contraseñas más exigentes:** mínimo 10 caracteres, ni comunes, ni parecidas al usuario, ni solo números.
- **Cabeceras de seguridad:** HSTS, `X-Frame-Options: DENY`, `X-Content-Type-Options`, `Content-Security-Policy` estricta y `Permissions-Policy` (`permisos/middleware.py`), cookies de sesión y CSRF con `HttpOnly`, `SameSite=Lax` y (en producción) `Secure`. Sesión de 8 horas.
- **Trazabilidad de los datos del empleado:** todo cambio manual sobre cargo, área, sección, correo, turno o vínculo activo queda en `CambioEmpleado`, con quién lo hizo y cuándo (no reemplaza a Zeus; ver más abajo).

Recomendaciones para producción que no vienen incluidas: HTTPS con certificado válido, un firewall o VPN delante del servidor, copias de seguridad periódicas de la base de datos, y, si el volumen de intentos de acceso lo justifica, una herramienta más completa como **django-axes** en vez del bloqueo casero de `views_auth.py`.

## Administración de personal (nuevo rol)

Grupo «Administración de personal» (`GRUPO_ADMIN_PERSONAL`): la persona encargada de que los datos del empleado estén al día cuando cambia de cargo, de área o de turno.

- **Editar empleados** (`/personal/`): cambia cargo, departamento, sección, correo, turno y si el vínculo está activo. Cédula, nombre y jefe inmediato siguen viniendo de Zeus y no se editan aquí, para que Zeus siga siendo la fuente de identidad. Cada cambio queda en el historial de auditoría, visible en la misma pantalla.
- **Turnos** (`/personal/turnos/`): el Club maneja dos horarios (por ejemplo, un turno de martes a sábado y otro de miércoles a domingo). Esta persona crea o edita cada turno —nombre, qué días de la semana trabaja y el día de descanso— y luego se lo asigna a cada empleado desde «Editar empleados». Si el Club cambia los días de un turno más adelante, se edita ahí mismo, sin tocar código.
- **Mi horario** (`/mi-horario/`, para cualquier persona): cada empleado ve a qué turno está asignado y qué días trabaja. El jefe inmediato ve además el turno de su equipo.

## Calendario real para pedir vacaciones

El formulario de vacaciones (`/vacaciones/nueva/`) ya no usa un campo de fecha en blanco: muestra un calendario navegable mes a mes (`static/js/calendario_vacaciones.js`), con los domingos y festivos de Colombia en rojo y los días ya pasados deshabilitados —el mismo cálculo que usa el servidor (`permisos/calendario.py`), para que lo que ve el empleado siempre coincida con lo que se valida al enviar.

## Imprimir el soporte de un permiso o de unas vacaciones

Desde el detalle de cualquier solicitud hay un botón «Imprimir / guardar como PDF» que abre una versión lista para imprimir, con el mismo formato del papel original (número, datos, firmas con fecha y hora) — útil si en algún momento se necesita el respaldo físico. Se abre en una pestaña nueva y lanza el diálogo de impresión automáticamente; desde ahí también se puede «Guardar como PDF».

## El logo del Club

Está en `static/img/logo_hatogrande.png` (fondo ya recortado a transparente) y aparece en el encabezado de cada página, en el login y en los formatos para imprimir. Para reemplazarlo, basta con sobrescribir ese archivo con el mismo nombre.

## Inicio de sesión

La pantalla de ingreso (`templates/registration/login.html`) tiene el logo del Club, un fondo con escenas ilustradas de golf y tenis que se alternan solas (en los colores del Club), y un selector de rol (Empleado, Jefe inmediato, Gestión Humana, Portería, Administración de personal). Ese selector es solo una comodidad de navegación —quien decide a dónde entra cada quien sigue siendo el grupo real asignado en Zeus o en el administrador—; si alguien marca un rol que no tiene, el sistema lo manda igual a lo que sí le corresponde.

Cuando el Club tenga fotografías propias de las instalaciones, se pueden poner como fondo real reemplazando los `background` de `.escena` en ese archivo por `background-image: url(...)`; no hace falta cambiar nada más de la lógica.

## Responsivo

Todas las páginas usan una sola columna centrada, con las tablas dentro de un contenedor con scroll horizontal (`.tabla-wrap`) para que quepan en el celular sin romper el diseño. El login y el menú también se ajustan a pantallas angostas. Antes de salir a producción, ábrelo desde un celular real (no solo achicando la ventana del navegador) para confirmar que todo se vea bien.

## Puesta en marcha (desarrollo)

```bash
python -m venv .venv && source .venv/bin/activate   # en Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py makemigrations permisos   # primera vez: genera las migraciones
python manage.py migrate
python manage.py createsuperuser
python manage.py sync_empleados            # usa zeus_empleados.csv de ejemplo
python manage.py shell -c "from permisos.personal import guardar_turno; from django.contrib.auth import get_user_model; guardar_turno(get_user_model().objects.filter(is_superuser=True).first(), None, 'Turno A', ['1','2','3','4','5'], 'Domingo y lunes', True)"  # turno de ejemplo, opcional
python manage.py runserver
python manage.py test                      # pruebas del flujo
python -m unittest permisos.test_calendario  # cálculos de calendario (sin Django)

**Nota:** este código se escribió sin poder ejecutar Django en el entorno de creación (no hay acceso a internet para instalarlo). Solo se verificó que compila; corre las pruebas antes de usarlo.
```

> Este esqueleto se escribió sin poder ejecutar Django en el entorno de creación.
> Solo se verificó que el código compila. Corre `python manage.py test` primero
> y corrige lo que aparezca.

## Vacaciones (fase 2)

Flujo: Empleado → Jefe inmediato → Gestión Humana → Registro. Al autorizar, las
vacaciones quedan registradas con fecha de reintegro y descuentan del saldo.

**Saldo** = días causados + ajustes − días autorizados − días en trámite.

- **Causados:** `VACACIONES_DIAS_POR_ANIO` por cada 360 días laborados desde la
  fecha de ingreso (año comercial). La fecha de ingreso viene de Zeus si la
  expone (columna `fecha_ingreso`) o la registra Gestión Humana en el admin.
- **Ajustes:** movimientos que Gestión Humana registra en **Saldos de vacaciones**
  (positivos o negativos, con motivo). No se editan ni se borran; un error se
  corrige con otro ajuste. Sirven para cargar lo disfrutado antes del portal.
- **Días hábiles:** se cuentan según `VACACIONES_DIAS_HABILES` y sin festivos de
  Colombia (`permisos/calendario.py` los calcula, incluidos los trasladados por
  la Ley Emiliani).
- **Fecha de reintegro:** el primer día hábil después del último día de vacaciones.
- **Cobertura:** al decidir, jefe y Gestión Humana ven quién más del equipo tiene
  vacaciones (aprobadas o en trámite) en esas fechas.
- Se vuelve a validar el saldo cuando Gestión Humana autoriza.

Saldos iniciales, con un CSV `cedula,dias_previos[,motivo]` (días ya disfrutados
o compensados antes del portal; crea ajustes negativos, todo o nada):

```bash
python manage.py cargar_saldos_iniciales saldos_iniciales.csv
```

### Parámetros que Gestión Humana debe confirmar

Están en `config/settings.py` como valores de partida, no como criterio legal.
Antes de producción, valídalos con Gestión Humana y el asesor laboral:

| Parámetro | Valor inicial | Qué decide |
|---|---|---|
| `VACACIONES_DIAS_POR_ANIO` | 15 | Días hábiles por año de servicio. |
| `VACACIONES_DIAS_HABILES` | lunes a sábado | Qué días de la semana cuentan (¿el sábado cuenta aunque no se trabaje?). |
| `VACACIONES_ANTIGUEDAD_MINIMA_DIAS` | 360 | Servicio mínimo antes del primer disfrute. |
| `VACACIONES_ANTELACION_DIAS` | 15 | Aviso mínimo entre la solicitud y el primer día. |
| `VACACIONES_MIN_DIAS_POR_SOLICITUD` | 6 | Mínimo por solicitud, salvo que use todo el saldo entero. |
| `VACACIONES_PERMITIR_ANTICIPO` | falso | Si puede pedir más días de los causados. |

Preguntas abiertas para el Club: acumulación de períodos, compensación en dinero,
personal por turnos (¿se cuenta el día de descanso rotativo?), y cómo se registran
las vacaciones colectivas.

## Roles

| Rol | Cómo se asigna |
|---|---|
| Empleado | Todo empleado sincronizado desde Zeus. |
| Jefe inmediato | Automático: es jefe quien tiene empleados a cargo en Zeus. |
| Gestión Humana | Grupo «Gestión Humana» (admin → Usuarios). |
| Portería | Grupo «Portería». Solo ve permisos **autorizados** que cubren hoy. |
| Administración de personal | Grupo «Administración de personal». Edita cargo, área, sección, correo, turno y vínculo activo de los empleados; también crea y edita los turnos. |

Para probar: entra al admin y agrega tu usuario al grupo que quieras probar
(«Gestión Humana», «Portería» o «Administración de personal»). Crea también
algunos **Tipos de permiso** (cita médica, diligencia personal, calamidad…) y,
si vas a probar vacaciones o turnos, al menos un **Turno** con sus días.

## Numeración desde 8838

El formato físico va en el No. 8837. Para continuar la numeración en PostgreSQL:

```sql
ALTER SEQUENCE permisos_solicitudpermiso_id_seq RESTART WITH 8838;
```

## Integración con Zeus Reloj

Todo está en `permisos/zeus.py`. **Solo lectura.** Dos opciones:

- `ZEUS_BACKEND=csv`: Zeus exporta un CSV (ver `zeus_empleados.csv`).
- `ZEUS_BACKEND=sql`: consulta directa con `ZEUS_ODBC_CONNECTION` y `ZEUS_SQL_QUERY`.

Los nombres de columnas son un supuesto hasta tener la documentación de Zeus.
Programa `python manage.py sync_empleados` (cron o Programador de tareas), por
ejemplo cada noche. Con `--desactivar-ausentes` se inactivan los que ya no
aparecen en Zeus. Los usuarios se crean con la identificación como usuario y
sin contraseña: habilita «restablecer contraseña» por correo o conecta SSO.

## Pantalla de ingreso (login)

`templates/registration/login.html` reproduce la estructura exacta de la
foto de referencia que dio el Club: foto de fondo a toda pantalla, una
tarjeta oscura semitransparente flotante (redondeada, casi a todo el alto
pero con margen arriba/abajo/derecha — no pegada a los bordes), y el logo
grande a la izquierda superpuesto al borde de la tarjeta.

**Sobre la foto de fondo, para ser honesto:** `static/img/fondos/1.jpg` es
la foto que tú mismo enviaste (casa club, lago, montañas), usada tal cual
y sin desenfoque — solo le quité la etiqueta "Made with AI" de la esquina
(clonando el cielo de al lado) para que no apareciera en el sistema. Como
la propia imagen viene marcada como generada por IA, no es una fotografía
real del Club; si tienes una foto real (tomada en el Club) prefieres usar
en su lugar, reemplázala con el mismo nombre de archivo y listo.

El sistema detecta sola cualquier foto que subas a `static/img/fondos/`
con los nombres `1.jpg`, `2.jpg`… hasta `6.jpg`, sin tocar HTML ni CSS (ver
`static/img/fondos/LEEME.txt`). Si subes varias, el login las va rotando.

El formulario no muestra un selector de rol visible (así queda igual al
diseño de referencia): el rol real de cada persona lo sigue dando su grupo en
Django, y `permisos/views.inicio` ya manda a cada quien a su pantalla según
ese rol real después de iniciar sesión — nadie necesita elegir nada. El
mecanismo para forzar un destino por rol sigue disponible en
`permisos/views_auth.py` (`ROLES_LOGIN`, `get_success_url`) por si algún día
quieres accesos directos tipo «/ingresar/?rol=porteria», pero no es necesario
para que cada quien llegue a lo suyo.

## Verificación hecha en esta entrega

Esta sesión de trabajo corrió sin salida a internet (ni `pip` ni `apt`
tuvieron red), así que no pude instalar Django aquí para correr
`python manage.py test`. Lo que sí verifiqué antes de entregar:

- Los 31 archivos `.py` del proyecto compilan sin errores de sintaxis
  (`python -m py_compile`).
- Las 10 pruebas de calendario (festivos reales de Colombia, días hábiles,
  causación de vacaciones) corren con Python puro, sin Django, y pasan:
  `python -m unittest permisos.test_calendario`.
- El nuevo login se revisó visualmente —logo, tarjeta, campos, selector de
  rol, mensaje de error y el diseño en celular— renderizando la plantilla
  fuera de Django con un navegador headless.
- Hay 44 pruebas más (`tests.py`, `tests_personal.py`, `tests_seguridad.py`,
  `tests_vacaciones.py`) que ya existían y cubren el flujo de aprobación, los
  turnos, el bloqueo de acceso y las vacaciones, pero no pude ejecutarlas en
  este entorno. Corre `python manage.py test` en el tuyo (con Django
  instalado) antes de confiar en el código para producción.

## Pendiente antes de producción

- **Acceso y contraseñas:** flujo de restablecimiento por correo o SSO (Microsoft/LDAP).
- **Soportes:** se guardan en `MEDIA_ROOT` y se entregan solo mediante la vista `soporte`, con control de acceso. Nunca expongas esa carpeta directamente en el servidor web. Pueden contener datos médicos.
- **Habeas data (Ley 1581):** política de tratamiento, autorización y tiempo de retención.
- **HTTPS**, `DJANGO_SECRET_KEY` propio y `DJANGO_DEBUG=0`.
- **Notificaciones:** hoy por correo (`EMAIL_HOST`, etc.). WhatsApp sería una fase posterior.
- **Pendiente:** escalamiento si el jefe no responde, escritura de novedades en Zeus, vacaciones colectivas y compensación en dinero.

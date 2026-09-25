from django.shortcuts import render


def csrf_fallo(request, reason=""):
    """Página bonita para cuando el token de seguridad de un formulario venció
    (por ejemplo, por dejar la pestaña abierta mucho tiempo o por un reinicio
    del servidor). En vez del error técnico de Django, mostramos un aviso
    claro con un botón para volver a intentar."""
    return render(request, "errores/csrf.html", status=403)

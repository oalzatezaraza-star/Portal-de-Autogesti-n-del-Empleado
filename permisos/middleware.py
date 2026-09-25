class CabecerasSeguridadMiddleware:
    """Cabeceras HTTP adicionales que no cubren los settings estándar de Django.

    Django ya pone X-Content-Type-Options, X-Frame-Options y HSTS a partir de
    settings.py. Aquí se agregan Permissions-Policy y una Content-Security-Policy
    estricta, porque las plantillas del portal no usan scripts ni estilos
    externos (todo el CSS y JS está en la propia plantilla).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        respuesta = self.get_response(request)
        respuesta.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
        )
        respuesta.setdefault("Permissions-Policy", "geolocation=(), camera=(), microphone=()")
        respuesta.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        return respuesta

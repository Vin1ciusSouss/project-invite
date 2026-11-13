"""Usar somente atrás do balanceador do PythonAnywhere."""
from ipaddress import ip_address


class PythonAnywhereProxy:
    def __init__(self, application):
        self.application = application

    def __call__(self, environ, start_response):
        # O balanceador do provedor sobrescreve X-Real-IP. X-Forwarded-For
        # pode conter valores enviados pelo cliente e não é usado aqui.
        real_ip = environ.get("HTTP_X_REAL_IP", "")
        try:
            environ["REMOTE_ADDR"] = str(ip_address(real_ip))
        except ValueError:
            pass
        return self.application(environ, start_response)

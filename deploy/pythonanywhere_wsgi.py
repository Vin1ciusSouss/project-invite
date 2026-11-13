"""Entrada WSGI do PythonAnywhere. Não inicia servidor nem altera o banco."""
import os
from pathlib import Path

from dotenv import load_dotenv

from app import create_app
from deploy.pythonanywhere_proxy import PythonAnywhereProxy

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=False)
if os.getenv("APP_ENV", "").strip().lower() != "production":
    raise RuntimeError("Defina APP_ENV=production no .env da hospedagem.")
hostname = os.getenv("PYTHONANYWHERE_HOST", "").strip()
if not hostname:
    raise RuntimeError("Configure PYTHONANYWHERE_HOST com o endereço mostrado na aba Web.")

application = create_app({"DEBUG": False, "TRUSTED_HOSTS": [hostname]})
application.wsgi_app = PythonAnywhereProxy(application.wsgi_app)

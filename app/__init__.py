import os
from pathlib import Path
from flask import Flask, render_template, request
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge, SecurityError
from flask_wtf.csrf import CSRFProtect
from dotenv import load_dotenv
from .extensions import db, migrate
from .routes import main

csrf = CSRFProtect()

def create_app(test_config=None):
    project_root = Path(__file__).resolve().parent.parent
    load_dotenv(project_root / ".env", override=False)
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    secret_key = os.getenv("SECRET_KEY", "").strip()
    admin_password_hash = os.getenv("ADMIN_PASSWORD_HASH", "").strip()
    is_production = app_env in {"prod", "production"}
    if is_production and (len(secret_key) < 32 or secret_key == "dev-change-this-key"):
        raise RuntimeError("Configure uma SECRET_KEY forte e aleatória com pelo menos 32 caracteres antes de iniciar em produção.")
    if is_production and not admin_password_hash:
        raise RuntimeError("Configure ADMIN_PASSWORD_HASH antes de iniciar em produção.")
    secure_cookie_value = os.getenv("SESSION_COOKIE_SECURE")
    session_cookie_secure = is_production or (
        secure_cookie_value is not None
        and secure_cookie_value.strip().lower() in {"1", "true", "yes", "on"}
    )
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=secret_key or "dev-change-this-key",
        APP_ENV=app_env,
        PUBLIC_SITE_URL=os.getenv("PUBLIC_SITE_URL", "").strip() or (
            "https://" + (os.getenv("PYTHONANYWHERE_HOST", "").strip() or "viniciussouss.pythonanywhere.com")
        ),
        ADMIN_PASSWORD_HASH=admin_password_hash,
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL") or "sqlite:///casamento.db",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=6 * 1024 * 1024,
        STYLESHEET_VERSION=str((Path(app.static_folder) / "css" / "style.css").stat().st_mtime_ns),
        NOTIFICATIONS_VERSION=str((Path(app.static_folder) / "js" / "notifications.js").stat().st_mtime_ns),
        GIFT_UPLOAD_FOLDER=os.getenv("GIFT_UPLOAD_FOLDER") or os.path.join(app.static_folder, "img", "presentes"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=session_cookie_secure,
        PREFERRED_URL_SCHEME="https" if app_env in {"prod", "production"} else "http",
    )
    if test_config:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)
    db.init_app(app)
    from . import models  # noqa: F401
    migrate.init_app(app, db, directory=str(project_root / "migrations"))
    csrf.init_app(app)
    app.register_blueprint(main)
    from .admin import admin
    app.register_blueprint(admin)

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        if request.path.startswith(("/admin", "/confirmar-presenca", "/convites/")):
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
        if app.config["APP_ENV"] in {"prod", "production"}:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    @app.errorhandler(RequestEntityTooLarge)
    def request_too_large(_error):
        return render_template("errors/request_too_large.html"), 413

    @app.errorhandler(HTTPException)
    def branded_http_error(error):
        messages = {
            400: ("Não foi possível concluir o envio", "Atualize a página do formulário e tente novamente."),
            403: ("Acesso não permitido", "Você não tem permissão para acessar esta página."),
            404: ("Página não encontrada", "O endereço pode estar incorreto ou a página não está mais disponível."),
            405: ("Vamos tentar novamente", "Abra a página pelo site e tente realizar a ação novamente."),
            429: ("Aguarde um momento", "Foram feitas muitas tentativas. Aguarde alguns minutos antes de tentar novamente."),
            500: ("Algo não saiu como esperado", "Não foi possível concluir sua solicitação agora. Tente novamente em alguns instantes."),
        }
        title, message = messages.get(error.code, ("Não foi possível abrir esta página", "Tente novamente em alguns instantes."))
        response = error.get_response()
        response.set_data(render_template("errors/http_error.html", error_code=error.code, error_title=title, error_message=message))
        response.content_type = "text/html; charset=utf-8"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(SecurityError)
    def invalid_access_address(_error):
        # An untrusted Host is rejected before Flask has a URL adapter, so
        # templates that use url_for cannot be rendered for this request.
        return "Endereço de acesso inválido.", 400, {"Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store"}

    from .commands import register_commands
    register_commands(app)

    return app


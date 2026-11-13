"""Gera os segredos diretamente na hospedagem, sem exibi-los no console."""
import argparse
from getpass import getpass
from pathlib import Path
import re
from secrets import token_hex
import sys

from werkzeug.security import generate_password_hash


def validate_hostname(value):
    hostname = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.(?:eu\.)?pythonanywhere\.com", hostname):
        raise argparse.ArgumentTypeError("Informe o domínio gratuito exibido na aba Web, sem https:// nem barras.")
    return hostname


def configure(project_root, hostname, password):
    hostname = validate_hostname(hostname)
    if not 12 <= len(password) <= 256:
        raise ValueError("A senha deve ter entre 12 e 256 caracteres.")
    env_path = project_root / ".env"
    if env_path.exists():
        raise FileExistsError("O .env já existe. Ele foi preservado; edite-o pelo painel Files se precisar ajustar a configuração.")
    data_directory = project_root.parent / "casamento-dados"
    uploads = data_directory / "presentes"
    uploads.mkdir(parents=True, exist_ok=True)
    database_uri = "sqlite:///" + (data_directory / "casamento.db").as_posix()
    content = (
        "APP_ENV=production\n"
        f"SECRET_KEY='{token_hex(32)}'\n"
        f"ADMIN_PASSWORD_HASH='{generate_password_hash(password)}'\n"
        f"DATABASE_URL='{database_uri}'\n"
        f"GIFT_UPLOAD_FOLDER='{uploads.as_posix()}'\n"
        f"PYTHONANYWHERE_HOST='{hostname}'\n"
    )
    with env_path.open("x", encoding="utf-8") as output:
        output.write(content)
    env_path.chmod(0o600)
    return env_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, type=validate_hostname)
    args = parser.parse_args()
    if sys.platform != "linux":
        parser.error("Execute este comando no console Bash do PythonAnywhere, depois de enviar o projeto.")
    project_root = Path(__file__).resolve().parent.parent
    if (project_root / ".env").exists():
        parser.error("O .env já existe e foi preservado. Edite-o no painel Files; não substitua segredos de um site em uso.")
    password = getpass("Escolha uma senha administrativa (mínimo 12 caracteres): ")
    if not 12 <= len(password) <= 256:
        parser.error("A senha deve ter entre 12 e 256 caracteres.")
    if password != getpass("Repita a senha administrativa: "):
        parser.error("As senhas não coincidem.")
    configure(project_root, args.host, password)
    print("Configuração criada. A senha e a chave secreta não foram exibidas.")
    print("Após decidir se vai importar dados, execute: python -m flask --app run.py preparar-banco")
    print("No arquivo WSGI da aba Web, use:\n")
    print("import sys")
    print(f"sys.path.insert(0, {str(project_root)!r})")
    print("from deploy.pythonanywhere_wsgi import application")


if __name__ == "__main__":
    main()

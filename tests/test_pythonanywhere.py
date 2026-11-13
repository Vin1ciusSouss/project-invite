import argparse
import os
from pathlib import Path
import runpy
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from dotenv import dotenv_values
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from deploy.configurar_pythonanywhere import configure, validate_hostname
from deploy.empacotar import build_package
from deploy.pythonanywhere_proxy import PythonAnywhereProxy


class PythonAnywhereTests(unittest.TestCase):
    def test_production_configuration_generates_secrets_without_overwriting(self):
        with TemporaryDirectory() as directory:
            project = Path(directory) / "project-casamento"
            project.mkdir()
            env_path = configure(project, "viniciussouss.pythonanywhere.com", "senha-longa-apenas-para-teste")
            values = dotenv_values(env_path)
            self.assertEqual(values["APP_ENV"], "production")
            self.assertEqual(values["PYTHONANYWHERE_HOST"], "viniciussouss.pythonanywhere.com")
            self.assertTrue(check_password_hash(values["ADMIN_PASSWORD_HASH"], "senha-longa-apenas-para-teste"))
            self.assertGreaterEqual(len(values["SECRET_KEY"]), 32)
            self.assertNotIn("senha-longa-apenas-para-teste", env_path.read_text())
            self.assertTrue(Path(values["GIFT_UPLOAD_FOLDER"]).is_dir())
            original = env_path.read_bytes()
            with self.assertRaises(FileExistsError):
                configure(project, "viniciussouss.pythonanywhere.com", "outra-senha-longa-para-teste")
            self.assertEqual(env_path.read_bytes(), original)

    def test_domain_requires_free_pythonanywhere_hostname(self):
        for hostname in ("https://site.pythonanywhere.com", "example.com", "site.pythonanywhere.com/", "site.pythonanywhere.com\nAPP_ENV=development"):
            with self.assertRaises(argparse.ArgumentTypeError):
                validate_hostname(hostname)
        self.assertEqual(validate_hostname("site.eu.pythonanywhere.com"), "site.eu.pythonanywhere.com")

    def test_archive_does_not_include_local_secrets_or_database(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app").mkdir()
            (root / "instance").mkdir()
            for relative in (".env", "app/.env.production", "app/local.db", "instance/casamento.db"):
                (root / relative).write_text("must-not-be-uploaded")
            (root / "app/__init__.py").write_text("# app")
            (root / ".env.example").write_text("SECRET_KEY=")
            destination = root / "dist/package.zip"
            build_package(root, destination)
            with ZipFile(destination) as archive:
                self.assertEqual(set(archive.namelist()), {"project-casamento/app/__init__.py", "project-casamento/.env.example"})

    def test_provider_proxy_uses_valid_real_ip_not_forwarded_for(self):
        addresses = []
        def application(environ, start_response):
            addresses.append(environ["REMOTE_ADDR"])
            return []
        wrapped = PythonAnywhereProxy(application)
        wrapped({"REMOTE_ADDR": "10.0.0.1", "HTTP_X_REAL_IP": "192.0.2.25", "HTTP_X_FORWARDED_FOR": "198.51.100.1"}, None)
        wrapped({"REMOTE_ADDR": "10.0.0.1", "HTTP_X_REAL_IP": "invalid", "HTTP_X_FORWARDED_FOR": "198.51.100.1"}, None)
        self.assertEqual(addresses, ["192.0.2.25", "10.0.0.1"])

    def test_wsgi_requires_production_and_restricts_host_without_creating_database(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "never-created.db"
            values = {
                "APP_ENV": "production", "SECRET_KEY": "test-secret-that-is-longer-than-32-characters",
                "ADMIN_PASSWORD_HASH": generate_password_hash("senha-para-testes"),
                "DATABASE_URL": "sqlite:///" + path.as_posix(),
                "PYTHONANYWHERE_HOST": "viniciussouss.pythonanywhere.com",
            }
            with patch.dict(os.environ, values):
                application = runpy.run_module("deploy.pythonanywhere_wsgi")["application"]
            client = application.test_client()
            self.assertEqual(client.get("/health", base_url="https://viniciussouss.pythonanywhere.com").status_code, 200)
            self.assertEqual(client.get("/health", base_url="https://other.example.com").status_code, 400)
            self.assertTrue(application.config["SESSION_COOKIE_SECURE"])
            self.assertFalse(application.debug)
            self.assertFalse(path.exists())
            with application.app_context():
                db.session.remove()
                db.engine.dispose()
            with patch.dict(os.environ, {**values, "APP_ENV": "development"}):
                with self.assertRaisesRegex(RuntimeError, "APP_ENV=production"):
                    runpy.run_module("deploy.pythonanywhere_wsgi")

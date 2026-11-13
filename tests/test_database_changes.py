from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.login_limits import reserve_attempt
from app.models import Gift, InviteGroup


class DatabaseChangesTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.database_path = self.root / "test.db"
        self.password = "senha-forte-para-teste"
        self.app = create_app({
            "TESTING": True, "WTF_CSRF_ENABLED": False,
            "SECRET_KEY": "chave-para-testes-de-banco",
            "ADMIN_PASSWORD_HASH": generate_password_hash(self.password),
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{self.database_path.as_posix()}",
        })
        self.app.instance_path = str(self.root / "instance")
        self.runner = self.app.test_cli_runner()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.directory.cleanup()

    def prepare(self):
        result = self.runner.invoke(args=["preparar-banco"])
        self.assertEqual(result.exit_code, 0, result.output + repr(result.exception))
        return result

    def test_factory_does_not_create_or_change_database(self):
        self.assertFalse(self.database_path.exists())

    def test_fresh_database_matches_models_and_preparation_is_idempotent(self):
        self.prepare()
        with self.app.app_context():
            self.assertEqual(Gift.query.count(), 4)
            with db.engine.connect() as connection:
                self.assertEqual(compare_metadata(MigrationContext.configure(connection), db.metadata), [])
            Gift.query.delete()
            db.session.commit()
        second = self.prepare()
        self.assertIn("já está atualizado", second.output)
        with self.app.app_context():
            self.assertEqual(Gift.query.count(), 0)
        self.assertFalse((self.root / "instance" / "backups").exists())

    def test_adopts_existing_schema_and_backs_up_before_upgrade(self):
        with self.app.app_context():
            db.create_all()
            db.session.add(InviteGroup(reference_name="Família existente", guest_names="Pessoa Convidada", invite_token="token-existente-que-deve-ser-preservado"))
            db.session.add(Gift(title="Presente reservado", status="reserved", reserved_by="Pessoa Convidada", image_filename="imagem-existente.png"))
            db.session.commit()
            # Simulate the database from before this change, without rate limit or version table.
            db.session.execute(text("DROP TABLE admin_login_limit"))
            db.session.commit()
        self.prepare()
        backups = list((self.root / "instance" / "backups").glob("*.db"))
        self.assertEqual(len(backups), 1)
        with closing(sqlite3.connect(backups[0])) as backup:
            tables = {row[0] for row in backup.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertNotIn("alembic_version", tables)
            self.assertNotIn("admin_login_limit", tables)
            self.assertEqual(backup.execute("SELECT reserved_by FROM gift").fetchone()[0], "Pessoa Convidada")
        with self.app.app_context():
            self.assertEqual(Gift.query.one().image_filename, "imagem-existente.png")
            self.assertEqual(InviteGroup.query.one().invite_token, "token-existente-que-deve-ser-preservado")
            self.assertIn("admin_login_limit", inspect(db.engine).get_table_names())
        self.prepare()
        self.assertEqual(len(list(backups[0].parent.glob("*.db"))), 1)

    def test_failed_backup_prevents_upgrade(self):
        with self.app.app_context():
            db.create_all()
            db.session.execute(text("DROP TABLE admin_login_limit"))
            db.session.commit()
        with patch("app.commands.sqlite3.connect", side_effect=OSError("backup indisponível")):
            result = self.runner.invoke(args=["preparar-banco"])
        self.assertNotEqual(result.exit_code, 0)
        with self.app.app_context():
            self.assertNotIn("admin_login_limit", inspect(db.engine).get_table_names())

    def test_upgrades_old_columns_and_preserves_guest_and_reservation(self):
        with self.app.app_context():
            with db.engine.begin() as connection:
                connection.execute(text("CREATE TABLE gift (id INTEGER PRIMARY KEY, title VARCHAR(120) NOT NULL, description VARCHAR(300) NOT NULL, amount_cents INTEGER NOT NULL, emoji VARCHAR(12) NOT NULL, status VARCHAR(20) NOT NULL, reserved_by VARCHAR(120), reserved_at DATETIME)"))
                connection.execute(text("INSERT INTO gift VALUES (1, 'Presente antigo', '', 1000, '', 'reserved', 'Pessoa Convidada', NULL)"))
                connection.execute(text("CREATE TABLE rsvp (id INTEGER PRIMARY KEY, guest_name VARCHAR(120) NOT NULL, email VARCHAR(254) NOT NULL, attendance VARCHAR(10) NOT NULL, guest_count INTEGER NOT NULL, message VARCHAR(500), created_at DATETIME NOT NULL)"))
                connection.execute(text("CREATE UNIQUE INDEX uq_rsvp_email ON rsvp(email)"))
                connection.execute(text("INSERT INTO rsvp VALUES (1, 'Pessoa Convidada', 'historico@example.com', 'yes', 2, 'Mensagem existente', '2026-11-12 12:00:00')"))
        self.prepare()
        with self.app.app_context():
            self.assertEqual(Gift.query.one().reserved_by, "Pessoa Convidada")
            self.assertEqual(db.session.execute(text("SELECT message FROM rsvp WHERE id = 1")).scalar_one(), "Mensagem existente")
            self.assertIn("invite_group_id", {column["name"] for column in inspect(db.engine).get_columns("rsvp")})
            self.assertNotIn("uq_rsvp_email", {index["name"] for index in inspect(db.engine).get_indexes("rsvp")})

    def test_login_limit_is_shared_between_clients_and_expires(self):
        self.prepare()
        with patch("app.login_limits.time.time", return_value=100000):
            for _ in range(5):
                client = self.app.test_client()
                self.assertEqual(client.post("/admin/login", data={"password": "errada"}).status_code, 200)
            blocked = self.app.test_client().post("/admin/login", data={"password": self.password})
            self.assertEqual(blocked.status_code, 429)
            self.assertEqual(blocked.headers["Retry-After"], "900")
            self.assertIn("Muitas tentativas".encode(), blocked.data)
        with patch("app.login_limits.time.time", return_value=100900):
            self.assertEqual(self.app.test_client().post("/admin/login", data={"password": self.password}).status_code, 302)

    def test_normalizes_legacy_foreign_key_without_losing_null_email(self):
        with self.app.app_context():
            db.create_all()
            db.session.add(InviteGroup(reference_name="Legado", guest_names="Pessoa Legada"))
            db.session.commit()
            with db.engine.begin() as connection:
                connection.execute(text("DROP TABLE admin_login_limit"))
                connection.execute(text("DROP TABLE rsvp"))
                connection.execute(text("CREATE TABLE rsvp (id INTEGER NOT NULL PRIMARY KEY, guest_name VARCHAR(120) NOT NULL, email VARCHAR(254), attendance VARCHAR(10) NOT NULL, invite_group_id INTEGER REFERENCES invite_group(id), guest_count INTEGER NOT NULL, companion_names TEXT NOT NULL, attendee_names TEXT NOT NULL, invite_guest_names TEXT NOT NULL, message VARCHAR(500), created_at DATETIME NOT NULL)"))
                connection.execute(text("INSERT INTO rsvp VALUES (1, 'Legado', NULL, 'yes', 1, 1, '', 'Pessoa Legada', 'Pessoa Legada', 'Preservar', '2026-11-12 12:00:00')"))
        self.prepare()
        with self.app.app_context():
            self.assertIsNone(db.session.execute(text("SELECT email FROM rsvp WHERE id=1")).scalar_one())
            self.assertEqual(db.session.execute(text("SELECT message FROM rsvp WHERE id=1")).scalar_one(), "Preservar")
            with db.engine.connect() as connection:
                self.assertEqual(compare_metadata(MigrationContext.configure(connection), db.metadata), [])

    def test_successful_login_clears_attempts(self):
        self.prepare()
        for _ in range(4):
            self.app.test_client().post("/admin/login", data={"password": "errada"})
        self.assertEqual(self.app.test_client().post("/admin/login", data={"password": self.password}).status_code, 302)
        for _ in range(5):
            self.assertEqual(self.app.test_client().post("/admin/login", data={"password": "errada"}).status_code, 200)

    def test_parallel_processes_cannot_exceed_limit(self):
        self.prepare()
        def attempt(_):
            with self.app.app_context():
                return reserve_attempt("192.0.2.1")
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(attempt, range(12)))
        self.assertEqual(results.count(0), 5)

    def test_forwarded_header_does_not_bypass_limit(self):
        self.prepare()
        for index in range(5):
            self.app.test_client().post("/admin/login", data={"password": "errada"}, headers={"X-Forwarded-For": f"192.0.2.{index}"})
        response = self.app.test_client().post("/admin/login", data={"password": "errada"}, headers={"X-Forwarded-For": "192.0.2.99"})
        self.assertEqual(response.status_code, 429)

"""Operações explícitas de manutenção; não executadas pelo servidor web."""
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from uuid import uuid4

import click
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from flask import current_app
from flask_migrate import upgrade
from sqlalchemy import inspect

from .extensions import db


def register_commands(app):
    @app.cli.command("preparar-banco")
    def prepare_database():
        """Faz backup do SQLite e aplica as migrações pendentes."""
        directory = current_app.extensions["migrate"].directory
        scripts = ScriptDirectory(directory)
        with db.engine.connect() as connection:
            tables = set(inspect(connection).get_table_names())
            current_heads = set(MigrationContext.configure(connection).get_current_heads())
        if current_heads == set(scripts.get_heads()):
            click.echo("O banco já está atualizado.")
            return

        if db.engine.dialect.name == "sqlite" and tables:
            database_path = db.engine.url.database
            if database_path and database_path != ":memory:":
                backup_directory = Path(current_app.instance_path) / "backups"
                backup_directory.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
                backup_path = backup_directory / f"casamento-{timestamp}-{uuid4().hex[:8]}.db"
                with closing(sqlite3.connect(database_path)) as source:
                    with closing(sqlite3.connect(backup_path)) as destination:
                        source.backup(destination)
                click.echo(f"Backup criado em: {backup_path}")

        upgrade(directory=directory)
        if not tables:
            from .seed import seed_gifts
            seed_gifts()
        click.echo("Banco atualizado com sucesso.")

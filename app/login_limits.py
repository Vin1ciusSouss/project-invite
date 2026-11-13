"""Limite persistente e atômico; não confia em cabeçalhos de proxy enviados pelo cliente."""
import hashlib
import hmac
import time

from flask import current_app
from sqlalchemy import case, delete, or_, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .extensions import db
from .models import AdminLoginLimit

MAX_ATTEMPTS = 5
WINDOW_SECONDS = 15 * 60


def _key(address):
    return hmac.new(
        current_app.secret_key.encode(), (address or "unknown").encode(), hashlib.sha256
    ).hexdigest()


def reserve_attempt(address):
    """Reserva uma tentativa antes de verificar a senha; retorna segundos de espera."""
    now = int(time.time())
    key = _key(address)
    table = AdminLoginLimit.__table__
    insert = sqlite_insert if db.engine.dialect.name == "sqlite" else postgres_insert
    expired = table.c.window_started <= now - WINDOW_SECONDS
    statement = insert(table).values(key=key, attempts=1, window_started=now)
    statement = statement.on_conflict_do_update(
        index_elements=[table.c.key],
        set_={
            "attempts": case((expired, 1), else_=table.c.attempts + 1),
            "window_started": case((expired, now), else_=table.c.window_started),
        },
        where=or_(expired, table.c.attempts < MAX_ATTEMPTS),
    ).returning(table.c.key)
    db.session.execute(delete(table).where(table.c.window_started < now - 86400, table.c.key != key))
    accepted = db.session.execute(statement).first() is not None
    started = None if accepted else db.session.execute(
        select(table.c.window_started).where(table.c.key == key)
    ).scalar_one()
    db.session.commit()
    return 0 if accepted else max(1, started + WINDOW_SECONDS - now)


def clear_attempts(address):
    db.session.execute(delete(AdminLoginLimit).where(AdminLoginLimit.key == _key(address)))
    db.session.commit()

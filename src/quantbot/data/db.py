"""Database engine/session factory (SQLAlchemy, lazy).

Importing this module does not require SQLAlchemy; only calling ``get_engine``
or ``session_scope`` does.  This keeps the analytics layer import-light.
"""

from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator

from quantbot.config import get_settings


@lru_cache(maxsize=1)
def get_engine():
    from sqlalchemy import create_engine

    settings = get_settings()
    return create_engine(settings.database_url, pool_pre_ping=True, future=True)


@lru_cache(maxsize=1)
def get_session_factory():
    from sqlalchemy.orm import sessionmaker

    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)


@contextmanager
def session_scope() -> Iterator:
    """Transactional session scope."""
    Session = get_session_factory()
    session = Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_schema(sql_path: str = "sql/schema.sql") -> None:
    """Apply the SQL schema (idempotent — uses CREATE TABLE IF NOT EXISTS)."""
    from pathlib import Path

    from sqlalchemy import text

    ddl = Path(sql_path).read_text()
    engine = get_engine()
    with engine.begin() as conn:
        for stmt in _split_sql(ddl):
            if stmt.strip():
                conn.execute(text(stmt))


def _split_sql(ddl: str) -> list[str]:
    # naive splitter sufficient for our schema (no procedural blocks)
    return [s for s in ddl.split(";") if s.strip() and not s.strip().startswith("--")]

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import DATABASE_URL


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _make_engine() -> Engine | None:
    if not DATABASE_URL:
        return None
    return create_engine(DATABASE_URL, pool_pre_ping=True, future=True)


engine: Engine | None = _make_engine()
SessionLocal = (
    sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    if engine is not None
    else None
)


def database_enabled() -> bool:
    return SessionLocal is not None


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a database session."""
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured.")
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional session for use inside service functions."""
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured.")
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Create tables if the database is configured (idempotent)."""
    if engine is None:
        return
    from app.db import models  # noqa: F401  (register models)

    Base.metadata.create_all(engine)

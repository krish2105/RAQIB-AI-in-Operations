from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from .config import settings


def make_engine(url: str | None = None):
    url = url or settings.database_url
    kwargs = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    eng = create_engine(url, **kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(eng, "connect")
        def _fk_on(dbapi_conn, _rec):  # pragma: no cover
            dbapi_conn.execute("PRAGMA journal_mode=WAL")

    return eng


engine = make_engine()


def init_db(eng=None) -> None:
    from . import models  # noqa: F401  (register tables)

    SQLModel.metadata.create_all(eng or engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session

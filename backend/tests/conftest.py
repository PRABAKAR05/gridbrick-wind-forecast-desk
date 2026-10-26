"""Shared fixtures: an isolated warehouse loaded from the committed seed."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base, get_session
from app.main import app
from app.services.ingest import load_seed


@pytest.fixture(scope="session")
def session_factory(tmp_path_factory: pytest.TempPathFactory) -> sessionmaker[Session]:
    db_path = tmp_path_factory.mktemp("gridbrick") / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)
    with factory() as session:
        seeded = load_seed(session)
    assert seeded["actuals"] > 0 and seeded["forecasts"] > 0
    return factory


@pytest.fixture(scope="session")
def client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    def override_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        test_client.close()
        app.dependency_overrides.clear()

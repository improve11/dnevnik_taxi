import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    # Isolate each test in its own SQLite database, avoiding the developer's data.
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    import app.main as main
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    test_engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(main, "engine", test_engine)
    monkeypatch.setattr(main, "SessionLocal", TestSession)
    empty_data_dir = Path(db_path).parent / (Path(db_path).stem + "_data")
    empty_data_dir.mkdir()
    monkeypatch.setattr(main, "DATA_DIR", empty_data_dir)

    with TestClient(main.app) as test_client:
        yield test_client

    test_engine.dispose()
    Path(db_path).unlink(missing_ok=True)
    import shutil
    shutil.rmtree(empty_data_dir, ignore_errors=True)


def trip_payload(**overrides):
    data = {
        "id": "test-1",
        "start": "2026-10-01T08:10:00+04:00",
        "end": "2026-10-01T08:32:00+04:00",
        "amount": 2400,
        "payment": "card",
        "commission": 360,
    }
    data.update(overrides)
    return data

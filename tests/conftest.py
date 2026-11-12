import os
import sys
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

os.environ['DATABASE_URL'] = 'sqlite://'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app import db, main

@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)
    db.Base.metadata.create_all(engine)
    db.SessionLocal.configure(bind=engine)
    monkeypatch.setattr(main, 'RAW_EXT', tmp_path)
    monkeypatch.setattr(main, 'LOG_FILE', tmp_path / 'ingest.log')
    yield
    engine.dispose()

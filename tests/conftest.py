import os
import sys
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.engine import make_url

os.environ['DATABASE_URL'] = 'sqlite://'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app import db, main

@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    mysql_url = os.environ.get('MYSQL_TEST_URL')
    if mysql_url:
        url = make_url(mysql_url)
        if url.host not in ('localhost', '127.0.0.1') or not (url.database or '').startswith('ai_jobs_test_'):
            raise ValueError('MySQL tests require a dedicated local ai_jobs_test_* database.')
        engine = db.build_engine(url)
    else:
        engine = create_engine('sqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)
    db.Base.metadata.create_all(engine)
    db.SessionLocal.configure(bind=engine)
    monkeypatch.setattr(main, 'RAW_EXT', tmp_path)
    monkeypatch.setattr(main, 'LOG_FILE', tmp_path / 'ingest.log')
    yield
    if mysql_url:
        db.Base.metadata.drop_all(engine)
    engine.dispose()

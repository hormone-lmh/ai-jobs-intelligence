from datetime import datetime

from app.db import Job, JobDetail, get_session


def test_database_preserves_long_unicode_and_microseconds():
    captured = datetime(2026, 11, 13, 12, 34, 56, 123456)
    body = '中文岗位 Python 🚀\n' * 7000
    with get_session() as session:
        job = Job(id=100, job_key='CaseKey', title='中文 AI 岗位', first_seen=captured, last_seen=captured)
        session.add(job)
        session.flush()
        session.add(JobDetail(job_id=job.id, job_key=job.job_key, jd_text=body, captured_at=captured))
        session.commit()
    with get_session() as session:
        detail = session.query(JobDetail).one()
        assert detail.jd_text == body
        assert detail.captured_at == captured
        assert session.get(Job, 100).first_seen == captured
        # A migrated explicit ID must not break subsequent ingestion IDs.
        job = Job(job_key='new-key', title='新增岗位')
        session.add(job)
        session.flush()
        assert job.id > 100
        session.rollback()
    with get_session() as session:
        assert session.query(Job).count() == 1

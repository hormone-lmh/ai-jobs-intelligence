from datetime import datetime
from fastapi.testclient import TestClient
from app import db, main


def seed():
    now = datetime.now()
    main._ingest_cards([{'href':'/job_detail/delete1.html','title_guess':'Python 工程师'},
                        {'href':'/job_detail/keep1.html','title_guess':'Java 工程师'}],now)
    main._ingest_detail('https://www.zhipin.com/job_detail/delete1.html',
                        {'sections':['熟悉 Python 与 PyTorch，有模型部署项目经验和良好沟通能力。']},now)


def test_delete_removes_dependents_statistics_and_blocks_recollection():
    seed()
    client=TestClient(main.app)
    assert client.delete('/api/jobs/delete1').json()['ok']
    assert client.delete('/api/jobs/delete1').json()['already_deleted']
    assert client.get('/api/jobs/delete1/detail').json()=={'ok':False,'reason':'job_not_found'}
    with db.get_session() as session:
        assert session.query(db.Job).one().job_key=='keep1'
        assert session.query(db.JobDetail).count()==0
        assert not session.query(db.SkillMention).filter_by(source='jd').count()
        assert session.query(db.DeletedJob).count()==1
    assert main.stats_overview()['jobs']==1
    assert main.stats_skills(50,'jd')['items']==[]
    # Both repeated extension messages and historical replay use these paths.
    result=main._ingest_cards([{'href':'/job_detail/delete1.html','title_guess':'Python 工程师'}],datetime.now())
    assert result=={'accepted':0,'updated':0,'skipped':1}
    payload={'url':'https://www.zhipin.com/job_detail/delete1.html','page_type':'detail',
             'detail':{'sections':['熟悉 Python 与 PyTorch，有模型部署项目经验和良好沟通能力。']}}
    response=client.post('/api/ingest/page',json=payload)
    assert response.json()['detail']['ignored']=='deleted_job'
    assert response.json()['detail']['jd_chars']==0
    assert client.post('/api/import/raw').status_code==200
    response=client.post('/api/import/jd',json={'url':payload['url'],'jd_text':payload['detail']['sections'][0]})
    assert response.status_code==409
    assert main.stats_overview()['jobs']==1


def test_delete_unknown_does_not_create_block_marker():
    client=TestClient(main.app)
    assert client.delete('/api/jobs/missing').status_code==404
    with db.get_session() as session:
        assert session.query(db.DeletedJob).count()==0

from datetime import datetime, timedelta
import json
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from app import main, db
from app.parsing import parse_card

NOW = datetime(2026, 11, 11, 12)
URL = 'https://www.zhipin.com/job_detail/test1.html'
def card(key='test1', title='Python engineer'):
    return {'href':f'/job_detail/{key}.html','title_guess':title}
def jd(text='职位要求：熟悉 Python 和 PyTorch，能够完成模型训练与部署。', when=NOW):
    return main._ingest_detail(URL, {'sections':[text], 'body_text':'推荐岗位要求 Kubernetes。'}, when)
def mentions(source):
    with db.get_session() as s:
        return {m.canonical for m in s.query(db.SkillMention).filter_by(source=source)}

def test_repeated_cards_deduplicate_jobs_and_skills():
    main._ingest_cards([card(),card()],NOW)
    main._ingest_cards([card()],NOW)
    with db.get_session() as s:
        assert s.query(db.Job).count()==1
        assert s.query(db.SkillMention).count()==1

def test_statistics_without_jd_are_explicitly_empty():
    main._ingest_cards([card(),card('test2','工程师')],NOW)
    assert main.stats_skills(30,'jd')['items']==[]
    assert main.stats_skills(30,'jd')['total_jobs']==0
    result=main.stats_skills(30,'summary')
    assert result['total_jobs']==2 and result['items'][0]['rate']==0.5

def test_jd_skill_replacement_and_independent_title_evidence():
    main._ingest_cards([card()],NOW)
    assert jd()['ok']
    assert {'Python','PyTorch'} <= mentions('jd')
    assert 'Kubernetes' not in mentions('jd')
    jd('职位要求：熟悉 Java 和 Docker，能够独立完成后端项目开发。',NOW+timedelta(hours=1))
    assert 'PyTorch' not in mentions('jd')
    assert 'Python' not in mentions('jd')
    assert 'Python' in mentions('title')
    assert {'Java','Docker'} <= mentions('jd')

def test_list_refresh_does_not_remove_jd_evidence():
    main._ingest_cards([card()],NOW)
    jd()
    main._ingest_cards([card(title='工程师')],NOW+timedelta(hours=1))
    assert 'Python' in mentions('jd')
    assert not mentions('title')

def test_jd_denominator_includes_no_skill_jd_and_filters():
    jd()
    main._ingest_detail('https://www.zhipin.com/job_detail/test2.html', {'sections':['岗位职责：负责团队日常工作协调及项目计划安排和沟通工作。']}, NOW)
    main._ingest_cards([card('test3')],NOW)
    result=main.stats_skills(30,'jd')
    assert result['total_jobs']==2 and result['sampled_jobs']==3
    assert next(x for x in result['items'] if x['skill']=='Python')['rate']==0.5
    assert main.stats_skills(30,'jd',city='不存在')['total_jobs']==0

def test_older_replay_cannot_replace_newer_details_or_list():
    main._ingest_cards([card(title='新岗位')],NOW)
    main._ingest_cards([card(title='旧岗位')],NOW-timedelta(days=1))
    jd('职位要求：熟悉 Java 和 Docker，能够独立完成后端项目开发。')
    assert jd(when=NOW-timedelta(days=1))['ignored']=='older_snapshot'
    detail=main.job_detail('test1')
    assert detail['job']['title']=='新岗位'
    assert 'PyTorch' not in mentions('jd')

def test_body_only_payload_rejected_and_previous_jd_preserved():
    jd()
    result=main._ingest_detail(URL,{'body_text':'Python '+'推荐职位 '*20},NOW)
    assert not result['ok']
    assert 'PyTorch' in main.job_detail('test1')['jd_text']

def test_manual_import_and_raw_replay(tmp_path):
    main._ingest_cards([card()],NOW)
    result=main.import_jd(main.ManualDetail(url=URL,jd_text='岗位要求：熟练掌握 Python 编程语言并具有实际开发项目经验。'))
    assert result['ok'] and result['detail']['ok']
    assert list(tmp_path.glob('page_*.json'))
    assert main.import_raw_files()['details']==1
    assert main.job_detail('test1')['has_jd']
    assert any(s['source']=='jd' for s in main.job_detail('test1')['skills'])

def test_ingest_rejects_unusable_details():
    with pytest.raises(HTTPException) as exc:
        main.ingest_page(main.PagePayload(url=URL,page_type='detail',detail={'sections':[]}))
    assert exc.value.status_code==422

@pytest.mark.parametrize('url',['https://evil.example/job_detail/a.html','javascript:alert(1)','https://www.zhipin.com.evil.example/job_detail/a.html','//evil.example/job_detail/a.html'])
def test_source_url_validation(url):
    assert parse_card({'href':url}) is None
    with pytest.raises(ValidationError):
        main.ManualDetail(url=url,jd_text='岗位要求：熟悉软件开发流程并具有相关开发经验。')

def test_pagination_returns_total_and_source_specific_filter():
    main._ingest_cards([card(),card('test2')],NOW)
    jd()
    result=main.list_jobs(skill='Python',source='jd',limit=1,offset=0)
    assert result['total']==1 and result['count']==1
    result=main.list_jobs(source='summary',limit=1,offset=1)
    assert result['total']==2 and result['count']==1


def test_detail_before_list_and_foreign_skill_ignored():
    jd()
    assert main.job_detail('test1')['job']['title']=='(待列表页补齐)'
    main._ingest_cards([card()],NOW)
    assert main.job_detail('test1')['job']['title']=='Python engineer'
    assert 'Kubernetes' not in mentions('jd')

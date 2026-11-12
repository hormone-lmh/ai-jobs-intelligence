from datetime import datetime
from app import db,main
from app.intelligence import Scope, Comparison, compare, companies

NOW=datetime(2026,11,12,10)
def seed():
    main._ingest_cards([
        {'href':'/job_detail/a.html','title_guess':'大模型工程师','html_head':'<span class="boss-name">公司甲</span><span class="company-location">北京·海淀</span>'},
        {'href':'/job_detail/b.html','title_guess':'Python工程师','html_head':'<span class="boss-name">公司乙</span><span class="company-location">上海·浦东</span>'},
        {'href':'/job_detail/c.html','title_guess':'大模型应用','html_head':'<span class="boss-name">公司甲</span><span class="company-location">北京·海淀</span>'}],NOW)
    main._ingest_detail('https://www.zhipin.com/job_detail/a.html',{'sections':['任职要求：掌握 Python 和 PyTorch，负责模型训练部署和项目开发。']},NOW)
    main._ingest_detail('https://www.zhipin.com/job_detail/b.html',{'sections':['任职要求：掌握 Python 和 Docker，负责后端系统设计开发部署。']},NOW)

def test_comparison_denominators_and_percentage_points():
    seed();r=compare(Comparison(left=Scope(city='北京'),right=Scope(city='上海')))
    assert r['left']['jobs']==2 and r['left']['jd_jobs']==1
    assert r['left']['coverage']==0.5
    skills={s['skill']:s for s in r['skills']}
    assert skills['PyTorch']['difference_pp']==100
    assert skills['Docker']['difference_pp']==-100
    assert skills['Python']['difference_pp']==0
    assert r['overlap_jobs']==0

def test_empty_cohort_is_missing_not_zero():
    seed();r=compare(Comparison(left=Scope(),right=Scope(city='深圳')))
    assert r['right']['coverage'] is None
    assert all(s['right_rate'] is None and s['difference_pp'] is None for s in r['skills'])
    assert r['warnings']

def test_overlap_and_literal_keyword():
    seed();r=compare(Comparison(left=Scope(),right=Scope(keyword='大模型')))
    assert r['overlap_jobs']==2
    r=compare(Comparison(left=Scope(keyword='%'),right=Scope(keyword='_')))
    assert r['left']['jobs']==r['right']['jobs']==0

def test_company_grouping_and_pagination():
    seed();r=companies(q='',city='',offset=0,limit=1)
    assert r['total']==2 and len(r['items'])==1
    assert r['items'][0]['company']=='公司甲'
    assert r['items'][0]['jobs']==2 and r['items'][0]['jd_jobs']==1
    assert companies(q='',city='上海',offset=0,limit=10)['total']==1

def test_company_exact_drilldown():
    seed();r=main.list_jobs(company='公司甲',limit=20,offset=0)
    assert r['total']==2
    assert main.stats_skills(30,'jd',company='公司甲')['total_jobs']==1

def test_city_options_count_whole_sample_and_exclude_missing():
    seed()
    main._ingest_cards([{'href':'/job_detail/no-city.html','title_guess':'无城市岗位'}],NOW)
    rows=main.city_options()['items']
    assert rows == [{'city':'北京','jobs':2},{'city':'上海','jobs':1}]

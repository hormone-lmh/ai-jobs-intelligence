"""样本公司与分组需求对比。所有技能比例以可用正文为分母。"""
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from .db import Job, JobDetail, SkillMention, get_session

router = APIRouter(prefix='/api/intelligence')

class Scope(BaseModel):
    keyword: str = Field(default='', max_length=100)
    city: str = Field(default='', max_length=40)
    company: str = Field(default='', max_length=200)

class Comparison(BaseModel):
    left: Scope
    right: Scope

def scoped(session, scope):
    query = session.query(Job)
    if scope.keyword.strip():
        # 转义 LIKE 通配符，搜索词按字面匹配。
        term = scope.keyword.strip().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
        query = query.filter(Job.title.like('%'+term+'%', escape='\\'))
    if scope.city.strip(): query = query.filter(Job.city == scope.city.strip())
    if scope.company.strip(): query = query.filter(Job.company == scope.company.strip())
    return query

def profile(session, scope):
    query = scoped(session, scope)
    ids = query.with_entities(Job.id)
    total = query.count()
    jd_ids = session.query(JobDetail.job_id).filter(JobDetail.job_id.in_(ids)).distinct()
    denominator = jd_ids.count()
    rows = (session.query(SkillMention.canonical, func.count(func.distinct(SkillMention.job_id)))
            .filter(SkillMention.job_id.in_(jd_ids), SkillMention.source == 'jd')
            .group_by(SkillMention.canonical).all())
    skills = {name:{'jobs':count, 'rate':count/denominator} for name,count in rows}
    distributions = {}
    for name, field in [('experience',Job.exp_text),('education',Job.degree_text)]:
        distributions[name] = [{'label':label or '未记录','jobs':n} for label,n in
            query.with_entities(field,func.count(Job.id)).group_by(field).order_by(func.count(Job.id).desc()).all()]
    return {'scope':scope.model_dump(), 'jobs':total, 'jd_jobs':denominator,
            'coverage':denominator/total if total else None,
            'companies':query.with_entities(Job.company).filter(Job.company.isnot(None),Job.company!='').distinct().count(),
            'skills':skills, **distributions}

@router.get('/companies')
def companies(q: str = '', city: str = '', offset: int = Query(0,ge=0), limit: int = Query(20,ge=1,le=100)):
    with get_session() as session:
        query=session.query(Job.company,func.count(Job.id).label('jobs'),func.max(Job.last_seen).label('last_seen')).filter(Job.company.isnot(None),Job.company!='')
        if q: query=query.filter(Job.company.contains(q, autoescape=True))
        if city: query=query.filter(Job.city==city)
        grouped=query.group_by(Job.company)
        total=grouped.count()
        rows=grouped.order_by(func.count(Job.id).desc(),Job.company).offset(offset).limit(limit).all()
        items=[]
        for row in rows:
            details=profile(session,Scope(company=row.company,city=city))
            skill_rows=sorted(details['skills'].items(),key=lambda x:(-x[1]['jobs'],x[0]))[:5]
            items.append({'company':row.company,'jobs':row.jobs,'jd_jobs':details['jd_jobs'],
                'last_seen':row.last_seen.isoformat(timespec='seconds') if row.last_seen else None,
                'skills':[{'skill':name,**value} for name,value in skill_rows]})
        return {'ok':True,'total':total,'items':items}

@router.post('/compare')
def compare(request: Comparison):
    with get_session() as session:
        left=profile(session,request.left);right=profile(session,request.right)
        overlap=scoped(session,request.left).filter(Job.id.in_(scoped(session,request.right).with_entities(Job.id))).count()
        skills=[]
        for skill in left['skills'].keys() | right['skills'].keys():
            a=left['skills'].get(skill,{'jobs':0,'rate':0})
            b=right['skills'].get(skill,{'jobs':0,'rate':0})
            ar=a['rate'] if left['jd_jobs'] else None
            br=b['rate'] if right['jd_jobs'] else None
            skills.append({'skill':skill,'left_jobs':a['jobs'],'right_jobs':b['jobs'],
                           'left_rate':ar,'right_rate':br,
                           'difference_pp':(ar-br)*100 if ar is not None and br is not None else None})
        skills.sort(key=lambda s:(-abs(s['difference_pp'] or 0),-s['left_jobs']-s['right_jobs'],s['skill']))
        warnings=[]
        if not left['jd_jobs'] or not right['jd_jobs']: warnings.append('至少一组没有岗位正文；缺失比例显示为“暂无数据”，不按 0% 比较。')
        if min(left['jd_jobs'],right['jd_jobs'])<30: warnings.append('至少一组正文样本少于 30 条，仅适合探索，不用于推断整个招聘市场。')
        if overlap: warnings.append(f'两组有 {overlap} 条重叠岗位，组间差异并非独立样本差异。')
        return {'ok':True,'left':left,'right':right,'overlap_jobs':overlap,'skills':skills,'warnings':warnings}

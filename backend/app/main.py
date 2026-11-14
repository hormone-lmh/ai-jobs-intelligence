"""本地服务：接收扩展上报 → 解析 → 入库 → 提供查询与统计。

设计要点：
  - 原始上报一律先落盘（data/raw/extension），可回放、可追溯
  - 结构化字段的解析规则在 parsing.py，不在扩展里，改规则不必重装扩展
  - 薪资数字被平台字体混淆时如实标记，不猜测、不解码
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func

from .db import IngestBatch, Job, JobDetail, SkillMention, DeletedJob, get_session, init_db
from .parsing import JOB_KEY_RE, parse_card
from .skills import get_matcher
from .intelligence import router as intelligence_router

ROOT = Path(__file__).resolve().parents[2]
RAW_EXT = Path(os.getenv("JOBS_RAW_DIR") or ROOT / "data" / "raw" / "extension")
RAW_EXT.mkdir(parents=True, exist_ok=True)
LOG_FILE = RAW_EXT / "ingest.log"

app = FastAPI(title="AI 岗位情报分析系统", version="0.3.0")
app.include_router(intelligence_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://www.zhipin.com", "http://127.0.0.1:8000", "http://localhost:8000"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()


class PagePayload(BaseModel):
    url: str
    page_type: Literal["list", "detail", "state"]
    captured_at: str | None = None
    cards: list[dict[str, Any]] = Field(default_factory=list, max_length=500)
    detail: dict[str, Any] | None = None
    total_hint: str | None = None

    @field_validator("url")
    @classmethod
    def check_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.netloc != "www.zhipin.com":
            raise ValueError("仅接受 https://www.zhipin.com 的来源链接")
        return value


class ManualDetail(BaseModel):
    url: str
    jd_text: str = Field(min_length=20, max_length=100000)

    _check_url = field_validator("url")(PagePayload.check_url.__func__)


def _log(line: str) -> None:
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _parse_time(s: str | None) -> datetime:
    if not s:
        return datetime.now()
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
    except Exception:
        return datetime.now()


def _upsert_job(session, parsed: dict[str, Any], captured_at: datetime) -> bool | None:
    """True 为新增，False 为更新，None 为用户已删除。"""
    job = session.query(Job).filter(Job.job_key == parsed["job_key"]).with_for_update().one_or_none()
    if session.query(DeletedJob.id).filter_by(job_key=parsed["job_key"]).first():
        return None
    created = job is None
    if created:
        job = Job(job_key=parsed["job_key"], first_seen=captured_at)
        session.add(job)
    elif job.title != "(待列表页补齐)" and job.last_seen and captured_at < job.last_seen:
        # 回放旧记录不得覆盖较新的字段。
        job.first_seen = min(job.first_seen or captured_at, captured_at)
        return False

    job.title = parsed["title"]
    job.company = parsed["company"] or job.company
    job.city = parsed["city"] or job.city
    job.area = parsed["area"] or job.area
    job.salary_raw = parsed["salary_raw"] or job.salary_raw
    if parsed["salary_raw"]:
        job.salary_masked = bool(parsed["salary_masked"])
    job.exp_text = parsed["exp_text"] or job.exp_text
    job.degree_text = parsed["degree_text"] or job.degree_text
    job.tags_json = json.dumps(parsed["tags"], ensure_ascii=False)
    job.url = parsed["url"]
    job.first_seen = min(job.first_seen or captured_at, captured_at)
    job.last_seen = max(job.last_seen or captured_at, captured_at)

    # 字段都赋完再 flush，避免 INSERT 时 title 仍为 NULL
    if created:
        session.flush()

    # 技能重算：标签与标题分别匹配，同一技能只留一条证据
    # 只重算 tag/title 来源，保留详情页正文（jd）提取的结论
    session.query(SkillMention).filter(
        SkillMention.job_id == job.id,
        SkillMention.source.in_(("tag", "title")),
    ).delete(synchronize_session=False)
    matcher = get_matcher()
    seen: set[str] = set()
    for tag in parsed["tags"]:
        for hit in matcher.extract(tag, "tag"):
            if hit["canonical"] in seen:
                continue
            seen.add(hit["canonical"])
            session.add(
                SkillMention(
                    job_id=job.id,
                    canonical=hit["canonical"],
                    alias=hit["alias"],
                    direction=hit["direction"],
                    source=hit["source"],
                    evidence=hit["evidence"],
                )
            )
    for hit in matcher.extract(parsed["title"], "title"):
        if hit["canonical"] in seen:
            continue
        seen.add(hit["canonical"])
        session.add(
            SkillMention(
                job_id=job.id,
                canonical=hit["canonical"],
                alias=hit["alias"],
                direction=hit["direction"],
                source=hit["source"],
                evidence=hit["evidence"],
            )
        )
    session.flush()  # 同批次重复职位必须看到上一条已写入的技能
    return created


def _ingest_cards(cards: list[dict[str, Any]], captured_at: datetime) -> dict[str, int]:
    accepted = updated = skipped = 0
    session = get_session()
    try:
        for card in cards:
            parsed = parse_card(card)
            if not parsed:
                skipped += 1
                continue
            result = _upsert_job(session, parsed, captured_at)
            if result is None:
                skipped += 1
            elif result:
                accepted += 1
            else:
                updated += 1
        session.commit()
    finally:
        session.close()
    return {"accepted": accepted, "updated": updated, "skipped": skipped}


def _ingest_detail(url: str, detail: dict[str, Any] | None, captured_at: datetime) -> dict[str, Any]:
    """详情页：把 JD 正文挂到对应岗位，并补充正文里才出现的技能。"""
    m = JOB_KEY_RE.search(url or "")
    if not m:
        return {"ok": False, "reason": "no_job_key"}
    job_key = m.group(1)

    detail = detail or {}
    sections = detail.get("sections") or []
    if not isinstance(sections, list) or any(not isinstance(s, str) for s in sections):
        return {"ok": False, "reason": "invalid_sections"}
    # 仅分析岗位正文段落；绝不回退到包含推荐岗位/导航的 body_text。
    sections = list(dict.fromkeys(s.strip() for s in sections if s.strip()))
    body = "\n\n".join(sections)
    headings = detail.get("headings") or []
    if len(body) > 100000:
        return {"ok": False, "reason": "body_too_large"}
    if len(body) < 20:
        return {"ok": False, "reason": "empty_body"}

    session = get_session()
    try:
        job = session.query(Job).filter(Job.job_key == job_key).with_for_update().one_or_none()
        if session.query(DeletedJob.id).filter_by(job_key=job_key).first():
            return {"ok": True, "job_key": job_key, "ignored": "deleted_job", "jd_chars": 0}
        if job is None:
            # 详情页先于列表页到达：先占位，后续列表上报会补齐字段
            job = Job(job_key=job_key, title="(待列表页补齐)", first_seen=captured_at, last_seen=captured_at, url=url)
            session.add(job)
            session.flush()

        snap = session.query(JobDetail).filter(JobDetail.job_id == job.id).one_or_none()
        if snap is not None and snap.captured_at and captured_at < snap.captured_at:
            return {"ok": True, "job_key": job_key, "ignored": "older_snapshot",
                    "jd_chars": len(snap.jd_text or "")}
        if snap is None:
            snap = JobDetail(job_id=job.id, job_key=job_key)
            session.add(snap)
        snap.headings = json.dumps(headings, ensure_ascii=False)
        snap.jd_text = body
        snap.sections_json = json.dumps(sections, ensure_ascii=False)
        snap.char_len = len(body)
        snap.captured_at = captured_at
        job.last_seen = max(job.last_seen or captured_at, captured_at)

        matcher = get_matcher()
        session.query(SkillMention).filter(
            SkillMention.job_id == job.id, SkillMention.source == "jd"
        ).delete(synchronize_session=False)
        # JD 与标题/标签证据独立保存，避免列表刷新使正文技能丢失。
        have: set[str] = set()
        for hit in matcher.extract(body, "jd"):
            if hit["canonical"] in have:
                continue
            have.add(hit["canonical"])
            session.add(
                SkillMention(
                    job_id=job.id,
                    canonical=hit["canonical"],
                    alias=hit["alias"],
                    direction=hit["direction"],
                    source="jd",
                    evidence=hit["evidence"],
                )
            )
        session.commit()
        return {
            "ok": True,
            "job_key": job_key,
            "jd_chars": len(body),
            "skills_current": len(have),
        }
    finally:
        session.close()


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "jobs-intel", "root": str(ROOT)}


@app.delete("/api/jobs/{job_key}")
def delete_job(job_key: str):
    with get_session() as session:
        job = session.query(Job).filter_by(job_key=job_key).with_for_update().one_or_none()
        if job is None:
            if session.query(DeletedJob.id).filter_by(job_key=job_key).first():
                return {"ok": True, "job_key": job_key, "already_deleted": True}
            raise HTTPException(status_code=404, detail={"reason": "岗位不存在"})
        session.add(DeletedJob(job_key=job_key))
        session.query(JobDetail).filter_by(job_id=job.id).delete(synchronize_session=False)
        session.query(SkillMention).filter_by(job_id=job.id).delete(synchronize_session=False)
        session.query(Job).filter_by(id=job.id).delete(synchronize_session=False)
        session.commit()
        return {"ok": True, "job_key": job_key}


@app.post("/api/ingest/page")
def ingest_page(p: PagePayload) -> dict[str, Any]:
    stamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S_%f")
    prefix = "state_" if p.page_type == "state" else "page_"
    path = RAW_EXT / f"{prefix}{stamp}.json"
    payload = json.loads(p.model_dump_json())
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    n_cards = len(p.cards)
    captured_at = _parse_time(p.captured_at)
    counts = {"accepted": 0, "updated": 0, "skipped": 0}
    detail_info = None
    if p.page_type == "detail":
        detail_info = _ingest_detail(p.url, p.detail, captured_at)
        if not detail_info["ok"]:
            raise HTTPException(status_code=422, detail=detail_info)
    elif p.page_type != "state" and p.cards:
        counts = _ingest_cards(p.cards, captured_at)

    session = get_session()
    try:
        session.add(
            IngestBatch(
                url=p.url,
                page_type=p.page_type,
                cards=n_cards,
                accepted=counts["accepted"],
                updated=counts["updated"],
                saved_file=path.name,
                created_at=datetime.now(),
            )
        )
        session.commit()
    finally:
        session.close()

    _log(f"{stamp} {p.page_type} cards={n_cards} new={counts['accepted']} upd={counts['updated']} url={p.url}")
    return {
        "ok": True,
        "cards": n_cards,
        "page_type": p.page_type,
        "saved": path.name,
        **counts,
        **({"detail": detail_info} if detail_info else {}),
    }


@app.post("/api/import/jd")
def import_jd(p: ManualDetail) -> dict[str, Any]:
    """用户粘贴目标岗位的职责/要求；采用与扩展一致的正文处理流程。"""
    result = ingest_page(PagePayload(
        url=p.url, page_type="detail", captured_at=datetime.now().astimezone().isoformat(),
        detail={"sections": [p.jd_text], "headings": ["手动录入岗位正文"]},
    ))
    if result.get("detail", {}).get("ignored") == "deleted_job":
        raise HTTPException(status_code=409, detail={"reason": "该岗位已被手动删除，不能重新导入"})
    return result


@app.post("/api/import/raw")
def import_raw_files() -> dict[str, Any]:
    """回放 data/raw/extension 下已有的 page_*.json（用于补历史与自检）。"""
    total_cards = accepted = updated = 0
    files = errors = details = 0
    for f in sorted(RAW_EXT.glob("page_*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("page_type") == "detail":
                result = _ingest_detail(data.get("url", ""), data.get("detail"), _parse_time(data.get("captured_at")))
                files += 1
                details += int(result["ok"])
                errors += int(not result["ok"])
                continue
            if data.get("page_type") != "list" or not data.get("cards"):
                continue
            files += 1
            total_cards += len(data["cards"])
            c = _ingest_cards(data["cards"], _parse_time(data.get("captured_at")))
            accepted += c["accepted"]
            updated += c["updated"]
        except Exception:
            errors += 1
            continue
    return {
        "ok": errors == 0,
        "files": files,
        "details": details,
        "cards": total_cards,
        "accepted": accepted,
        "updated": updated,
        "errors": errors,
    }


@app.get("/api/jobs")
def list_jobs(
    q: str | None = None,
    city: str | None = None,
    skill: str | None = None,
    source: Literal["jd", "summary"] = "jd",
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    company: str | None = None,
) -> dict[str, Any]:
    session = get_session()
    try:
        query = session.query(Job)
        if q:
            like = f"%{q}%"
            query = query.filter((Job.title.like(like)) | (Job.company.like(like)))
        if city:
            query = query.filter(Job.city == city)
        if company:
            query = query.filter(Job.company == company)
        if skill:
            query = query.join(SkillMention).filter(
                SkillMention.canonical == skill,
                SkillMention.source.in_(["jd"] if source == "jd" else ["tag", "title"]),
            ).distinct()
        total = query.count()
        rows = query.order_by(Job.last_seen.desc(), Job.id.desc()).offset(offset).limit(limit).all()
        ids_with_jd = {x[0] for x in session.query(JobDetail.job_id).distinct().all()}
        return {
            "ok": True,
            "count": len(rows),
            "total": total,
            "items": [
                {
                    "job_key": r.job_key,
                    "title": r.title,
                    "company": r.company,
                    "city": r.city,
                    "area": r.area,
                    "salary": r.salary_raw,
                    "salary_masked": r.salary_masked,
                    "exp": r.exp_text,
                    "degree": r.degree_text,
                    "tags": json.loads(r.tags_json or "[]"),
                    "url": r.url,
                    "first_seen": r.first_seen.isoformat(timespec="seconds") if r.first_seen else None,
                    "last_seen": r.last_seen.isoformat(timespec="seconds") if r.last_seen else None,
                    "has_jd": r.id in ids_with_jd,
                }
                for r in rows
            ],
        }
    finally:
        session.close()


@app.get("/api/jobs/{job_key}/detail")
def job_detail(job_key: str) -> dict[str, Any]:
    session = get_session()
    try:
        job = session.query(Job).filter(Job.job_key == job_key).one_or_none()
        if job is None:
            return {"ok": False, "reason": "job_not_found"}
        snap = session.query(JobDetail).filter(JobDetail.job_id == job.id).one_or_none()
        return {
            "ok": True,
            "job": {
                "job_key": job.job_key,
                "title": job.title,
                "company": job.company,
                "area": job.area,
                "salary": job.salary_raw,
                "salary_masked": job.salary_masked,
                "exp": job.exp_text,
                "degree": job.degree_text,
                "tags": json.loads(job.tags_json or "[]"),
                "url": job.url,
            },
            "has_jd": snap is not None,
            "jd_text": snap.jd_text if snap else None,
            "char_len": snap.char_len if snap else 0,
            "sections": json.loads(snap.sections_json or "[]") if snap else [],
            "headings": json.loads(snap.headings or "[]") if snap else [],
            "captured_at": snap.captured_at.isoformat(timespec="seconds") if snap else None,
            "skills": [
                {"skill": m.canonical, "source": m.source, "evidence": m.evidence}
                for m in session.query(SkillMention).filter(SkillMention.job_id == job.id)
                .order_by(SkillMention.source, SkillMention.canonical).all()
            ],
        }
    finally:
        session.close()


@app.get("/api/stats/overview")
def stats_overview() -> dict[str, Any]:
    session = get_session()
    try:
        jobs = session.query(func.count(Job.id)).scalar() or 0
        companies = session.query(func.count(func.distinct(Job.company))).scalar() or 0
        cities = session.query(func.count(func.distinct(Job.city))).scalar() or 0
        skills = session.query(func.count(func.distinct(SkillMention.canonical))).scalar() or 0
        masked = session.query(func.count(Job.id)).filter(Job.salary_masked.is_(True)).scalar() or 0
        last = session.query(func.max(Job.last_seen)).scalar()
        batches = session.query(func.count(IngestBatch.id)).scalar() or 0
        return {
            "ok": True,
            "jobs": jobs,
            "jd_jobs": session.query(func.count(func.distinct(JobDetail.job_id))).scalar() or 0,
            "companies": companies,
            "cities": cities,
            "skills": skills,
            "salary_unresolved": masked,
            "batches": batches,
            "last_seen": last.isoformat(timespec="seconds") if last else None,
        }
    finally:
        session.close()


@app.get("/api/filters/cities")
def city_options() -> dict[str, Any]:
    """城市选项来自全库，不受当前城市筛选影响；数量为样本职位数。"""
    with get_session() as session:
        rows = (session.query(Job.city, func.count(Job.id))
                .filter(Job.city.isnot(None), Job.city != "")
                .group_by(Job.city)
                .order_by(func.count(Job.id).desc(), Job.city).all())
        return {"ok": True, "items": [{"city": city, "jobs": count} for city, count in rows]}


@app.get("/api/stats/skills")
def stats_skills(
    limit: int = Query(30, ge=1, le=200),
    source: Literal["jd", "summary"] = "jd",
    q: str | None = None,
    city: str | None = None,
    company: str | None = None,
) -> dict[str, Any]:
    session = get_session()
    try:
        eligible = session.query(Job.id)
        if q:
            eligible = eligible.filter((Job.title.like(f"%{q}%")) | (Job.company.like(f"%{q}%")))
        if city:
            eligible = eligible.filter(Job.city == city)
        if company:
            eligible = eligible.filter(Job.company == company)
        sampled = eligible.count()
        if source == "jd":
            eligible = eligible.filter(Job.id.in_(session.query(JobDetail.job_id)))
        # 摘要口径包括有标题但无技能命中的岗位，不能以命中技能的岗位作分母。
        total = eligible.count()
        rows = (
            session.query(SkillMention.canonical, func.count(func.distinct(SkillMention.job_id)).label("n"))
            .filter(SkillMention.job_id.in_(eligible),
                    SkillMention.source.in_(["jd"] if source == "jd" else ["tag", "title"]))
            .group_by(SkillMention.canonical)
            .order_by(func.count(func.distinct(SkillMention.job_id)).desc())
            .limit(limit)
            .all()
        )
        return {
            "ok": True,
            "total_jobs": total,
            "sampled_jobs": sampled,
            "source": source,
            "items": [
                {
                    "skill": c,
                    "jobs": n,
                    "rate": round(n / total, 4) if total else 0,
                }
                for c, n in rows
            ],
        }
    finally:
        session.close()


@app.get("/api/ingest/stats")
def ingest_stats() -> dict[str, Any]:
    files = sorted(RAW_EXT.glob("page_*.json"))
    total_cards = 0
    last = None
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            total_cards += len(data.get("cards") or [])
            last = data.get("captured_at") or f.name
        except Exception:
            continue
    return {"ok": True, "pages": len(files), "cards": total_cards, "last": last}


# 静态页面必须最后挂载，否则会吞掉上面的 /api 路由
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

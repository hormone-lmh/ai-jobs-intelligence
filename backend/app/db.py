"""数据模型与会话（SQLite / MySQL + SQLAlchemy 2.0）。

设计遵循 docs/00-技术方案.md §3：
  - job_posting   一个岗位一行，按平台职位 ID 去重
  - skill_mention 技能证据，保留命中来源与原文片段
  - ingest_batch  一次上报的元信息，用于追溯与失败排查
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    func,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.engine import make_url
from sqlalchemy.dialects.mysql import DATETIME, LONGTEXT

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

_default_db = str(ROOT / "data" / "jobs.db").replace("\\", "/")
DB_URL = os.getenv("DATABASE_URL") or f"sqlite:///{_default_db}"

def build_engine(url):
    options = {"pool_pre_ping": True}
    if make_url(url).get_backend_name() == "sqlite":
        options["connect_args"] = {"check_same_thread": False}
    else:
        options["pool_recycle"] = 1800
    return create_engine(url, **options)


engine = build_engine(DB_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
Base = declarative_base()
# MySQL 默认 DATETIME 丢失微秒，TEXT 也容纳不下允许提交的长篇中文 JD。
DateTime = DateTime().with_variant(DATETIME(fsp=6), "mysql")
Text = Text().with_variant(LONGTEXT(), "mysql")


class Job(Base):
    __tablename__ = "job_posting"

    id = Column(Integer, primary_key=True)
    job_key = Column(String(64), unique=True, index=True, nullable=False)  # 平台职位 ID
    title = Column(String(200), nullable=False)
    company = Column(String(200), index=True)
    city = Column(String(40), index=True)
    area = Column(String(160))
    salary_raw = Column(String(80))
    salary_masked = Column(Boolean, default=False)  # 数字被字体混淆，未能还原
    exp_text = Column(String(40))
    degree_text = Column(String(40))
    tags_json = Column(Text)      # 平台给出的标签原文（JSON 数组）
    url = Column(String(300))
    source_channel = Column(String(40), default="extension")
    first_seen = Column(DateTime, default=datetime.now)
    last_seen = Column(DateTime, default=datetime.now)

    mentions = relationship("SkillMention", back_populates="job", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("job_key", name="uq_job_key"),)


class SkillMention(Base):
    __tablename__ = "skill_mention"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("job_posting.id"), index=True, nullable=False)
    canonical = Column(String(80), index=True, nullable=False)
    alias = Column(String(80))          # 实际命中的写法
    direction = Column(String(40), index=True)
    source = Column(String(20))         # tag / title / jd
    evidence = Column(String(200))      # 命中处的原文片段

    job = relationship("Job", back_populates="mentions")


class IngestBatch(Base):
    __tablename__ = "ingest_batch"

    id = Column(Integer, primary_key=True)
    url = Column(String(400))
    page_type = Column(String(20))
    cards = Column(Integer, default=0)
    accepted = Column(Integer, default=0)   # 新增
    updated = Column(Integer, default=0)    # 已存在而更新
    saved_file = Column(String(120))
    created_at = Column(DateTime, default=datetime.now)


class JobDetail(Base):
    """详情页 JD 快照。同一岗位保留最近一次正文，用于「看岗位要求」。"""

    __tablename__ = "job_detail"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("job_posting.id"), index=True, nullable=False)
    job_key = Column(String(64), index=True)
    headings = Column(Text)      # 段落标题 JSON
    jd_text = Column(Text)       # 全文
    sections_json = Column(Text) # 分段 JSON
    char_len = Column(Integer, default=0)
    captured_at = Column(DateTime, default=datetime.now)


class DeletedJob(Base):
    """仅保存删除标记，防止插件或原始记录回放重新导入岗位。"""
    __tablename__ = "deleted_job"
    id = Column(Integer, primary_key=True)
    job_key = Column(String(64), unique=True, index=True, nullable=False)
    deleted_at = Column(DateTime, default=datetime.now, nullable=False)


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_session():
    return SessionLocal()

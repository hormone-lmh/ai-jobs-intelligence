"""把扩展上报的卡片原样数据解析成结构化字段。

扩展只负责"看到什么交什么"，字段规则全部在这里，改规则不必重装扩展。
优先从 html_head 里按 class 取值（最准），失败时退回整段文本解析。
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlparse

PUA_RE = re.compile(r"[\ue000-\uf8ff]")
TAG_RE = re.compile(r"<[^>]+>")

EXP_RE = re.compile(r"(经验不限|在校/应届|应届生|\d+\s*[-~]\s*\d+\s*年|\d+\s*年以内|\d+\s*年以上)")
DEGREE_RE = re.compile(r"(学历不限|本科|硕士|大专|博士|中专/中技|高中|初中)")
AREA_RE = re.compile(r"([\u4e00-\u9fa5]{2,8}(?:·[\u4e00-\u9fa5A-Za-z0-9]{1,12}){1,3})\s*$")
JOB_KEY_RE = re.compile(r"/job_detail/([0-9A-Za-z_\-]+)\.html")


def _strip(s: str | None) -> str:
    return TAG_RE.sub("", s or "").strip()


def _field(html: str, cls: str) -> str | None:
    """取 class="xxx" 的元素内部文本（不跨元素嵌套做严谨解析，够用）。"""
    m = re.search(r'class="%s"[^>]*>(.*?)</(?:a|span|div|li)>' % re.escape(cls), html, re.S)
    return _strip(m.group(1)) if m else None


def _tag_list(html: str) -> list[str]:
    m = re.search(r'<ul[^>]*class="tag-list"[^>]*>(.*?)</ul>', html, re.S)
    if not m:
        return []
    return [t for t in (_strip(x) for x in re.findall(r"<li[^>]*>(.*?)</li>", m.group(1), re.S)) if t]


def _split_area(area: str | None) -> tuple[str | None, str | None]:
    if not area:
        return None, None
    parts = [p.strip() for p in area.split("·") if p.strip()]
    if not parts:
        return None, None
    city = parts[0]
    rest = "·".join(parts[1:]) or None
    return city, rest


def _salary_text(raw: str | None) -> tuple[str | None, bool]:
    """返回 (展示用薪资原文, 是否被字体混淆)。

    BOSS 把数字换成 U+E03x 私有区字符，文本层拿不到真实数字。
    这里如实标记，不猜测、不解码。
    """
    if not raw:
        return None, False
    masked = bool(PUA_RE.search(raw))
    # 把私有区字符替换成 □，让"缺了几位"看得出来
    shown = raw
    for ch in PUA_RE.findall(raw):
        shown = shown.replace(ch, "□")
    return shown, masked


def parse_card(card: dict[str, Any]) -> dict[str, Any] | None:
    href = card.get("href")
    if not isinstance(href, str) or not href:
        return None
    href = urljoin("https://www.zhipin.com", href)
    location = urlparse(href)
    if location.scheme != "https" or location.netloc != "www.zhipin.com":
        return None
    m = JOB_KEY_RE.search(href)
    if not m:
        return None
    job_key = m.group(1)

    html = card.get("html_head") or ""
    text = (card.get("text") or "").replace("\u3000", " ")

    title = _field(html, "job-name") or card.get("title_guess")
    salary_raw = _field(html, "job-salary")
    company = _field(html, "boss-name")
    area = _field(html, "company-location")

    tags = _tag_list(html)

    # 兜底：从整段文本补
    if not title:
        idx = text.find("-")
        title = text[:idx].strip() if idx > 0 else text[:40]

    if not area:
        am = AREA_RE.search(text)
        area = am.group(1) if am else None

    if not salary_raw:
        sm = re.search(r"([^\s]*?K(?:\s*·\s*[^\s]*?薪)?)", text)
        salary_raw = sm.group(1) if sm else None

    exp_text = next((t for t in tags if EXP_RE.fullmatch(t.strip())), None)
    degree_text = next((t for t in tags if DEGREE_RE.fullmatch(t.strip())), None)
    if not exp_text:
        em = EXP_RE.search(text)
        exp_text = em.group(1).replace(" ", "") if em else None
    if not degree_text:
        dm = DEGREE_RE.search(text)
        degree_text = dm.group(1) if dm else None

    skills_tags = [t for t in tags if t not in (exp_text, degree_text)]

    salary_shown, salary_masked = _salary_text(salary_raw)
    city, district = _split_area(area)

    return {
        "job_key": job_key,
        "title": title or "(无标题)",
        "company": company,
        "city": city,
        "area": area,
        "salary_raw": salary_shown,
        "salary_masked": salary_masked,
        "exp_text": exp_text,
        "degree_text": degree_text,
        "tags": skills_tags,
        "url": "https://www.zhipin.com" + href if href.startswith("/") else href,
    }

"""技能提取：以 config/taxonomy.yaml 为词典做规则匹配。

约束（见 taxonomy.yaml 顶部注释）：
  - 拉丁缩写的边界不能用 \\b（中文与字母同属 \\w），改用前后非字母数字断言
  - risk 字段列出的词（如 RAGFlow、torchvision）不参与合并计数
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

import yaml

ROOT = Path(__file__).resolve().parents[2]
TAXONOMY_PATH = ROOT / "config" / "taxonomy.yaml"


def _build_pattern(alias: str) -> re.Pattern:
    esc = re.escape(alias).replace(r"\ ", r"[ ]*")
    if re.fullmatch(r"[A-Za-z0-9 .\-_/+#]+", alias):
        # 纯拉丁/符号别名：用非字母数字断言代替 \b
        return re.compile(r"(?<![A-Za-z0-9])" + esc + r"(?![A-Za-z0-9])", re.I)
    return re.compile(esc, re.I)


class SkillMatcher:
    def __init__(self, path: Path = TAXONOMY_PATH):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.version = raw.get("version")
        self.directions = {d["id"]: d["name"] for d in raw.get("directions", [])}
        self.entries: list[dict[str, Any]] = []
        for s in raw.get("skills", []):
            risks = s.get("risk") or []
            for alias in s.get("aliases", []):
                self.entries.append(
                    {
                        "canonical": s["canonical"],
                        "alias": alias,
                        "direction": s.get("direction") or [],
                        "category": s.get("category"),
                        "pattern": _build_pattern(alias),
                        "risk": risks,
                    }
                )

    def _risk_spans(self, text: str, risks: Iterable[str]) -> list[tuple[int, int]]:
        spans = []
        for r in risks:
            for m in re.finditer(re.escape(r), text, re.I):
                spans.append(m.span())
        return spans

    def extract(self, text: str, source: str) -> list[dict[str, Any]]:
        """返回命中列表；同一 canonical 在同一来源里只保留第一次命中。"""
        if not text:
            return []
        hits: list[dict[str, Any]] = []
        seen: set[str] = set()
        for e in self.entries:
            if e["canonical"] in seen:
                continue
            risk_spans = self._risk_spans(text, e["risk"]) if e["risk"] else []
            for m in e["pattern"].finditer(text):
                span = m.span()
                if any(rs[0] <= span[0] and span[1] <= rs[1] for rs in risk_spans):
                    continue  # 落在被排除的复合词里
                ctx = text[max(0, span[0] - 12): min(len(text), span[1] + 12)].strip()
                hits.append(
                    {
                        "canonical": e["canonical"],
                        "alias": e["alias"],
                        "direction": ",".join(e["direction"]),
                        "category": e["category"],
                        "source": source,
                        "evidence": ctx[:200],
                    }
                )
                seen.add(e["canonical"])
                break
        return hits


_matcher: SkillMatcher | None = None


def get_matcher() -> SkillMatcher:
    global _matcher
    if _matcher is None:
        _matcher = SkillMatcher()
    return _matcher

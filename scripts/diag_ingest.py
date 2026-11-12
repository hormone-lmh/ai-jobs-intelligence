"""诊断入库失败：逐步跑解析 → 入库，暴露真实异常。"""

import glob
import json
import sys
import traceback
from datetime import datetime

sys.path.insert(0, r"F:\岗位搜集\backend")

from app.parsing import parse_card
from app.skills import get_matcher

files = sorted(glob.glob(r"F:\岗位搜集\data\raw\extension\page_*.json"))
if not files:
    raise SystemExit("no page file")
data = json.load(open(files[-1], encoding="utf-8"))
print(f"file={files[-1]} cards={len(data['cards'])}\n")

print("=== 1. parse_card ===")
for c in data["cards"][:3]:
    try:
        print(json.dumps(parse_card(c), ensure_ascii=False))
    except Exception:
        traceback.print_exc()

print("\n=== 2. matcher ===")
try:
    m = get_matcher()
    print(f"entries={len(m.entries)}")
    print(json.dumps(m.extract("Python工程师+包吃三餐", "title"), ensure_ascii=False))
    print(json.dumps(m.extract("爬虫经验", "tag"), ensure_ascii=False))
except Exception:
    traceback.print_exc()

print("\n=== 3. db import ===")
try:
    from app.db import get_session, init_db
    from app.main import _ingest_cards

    init_db()
    res = _ingest_cards(data["cards"], datetime.now())
    print(res)
except Exception:
    traceback.print_exc()

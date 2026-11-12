"""诊断：BOSS 薪资数字为什么在文本里缺失。

检查原始 JSON 中 job-salary 节点的真实码点：
  - 若中间是 U+E000..U+F8FF（私有区），说明是字体混淆，需要映射表才能还原
  - 若真的为空，说明数字由 CSS/图片生成，无法从文本取
"""

import glob
import json
import re

FILES = sorted(glob.glob(r"F:\岗位搜集\data\raw\extension\page_*.json"))
if not FILES:
    raise SystemExit("no page_*.json")

target = FILES[-1]
data = json.load(open(target, encoding="utf-8"))
print(f"file = {target}")
print(f"cards = {len(data.get('cards') or [])}\n")

PAT = re.compile(r'class="job-salary">([^<]*)</span>')
LIST_PAT = re.compile(r'<ul[^>]*class="tag-list"[^>]*>(.*?)</ul>', re.S)
LI_PAT = re.compile(r"<li[^>]*>(.*?)</li>", re.S)

for card in data["cards"][:6]:
    html = card.get("html_head") or ""
    text = card.get("text") or ""
    m = PAT.search(html)
    if m:
        raw = m.group(1)
        print(f"[{card['index']}] salary_html = {raw!r}")
        print(f"     codepoints = {[hex(ord(c)) for c in raw]}")
    else:
        print(f"[{card['index']}] salary_html = <not found>")

    tm = LIST_PAT.search(html)
    tags = [x.strip() for x in LI_PAT.findall(tm.group(1))] if tm else []
    print(f"     tags = {tags}")

    # text 里 '-K' 附近是否也有隐藏字符
    idx = text.find("-K")
    if idx >= 0:
        seg = text[max(0, idx - 6): idx + 4]
        print(f"     text_seg = {seg!r} codepoints={[hex(ord(c)) for c in seg]}")
    print()

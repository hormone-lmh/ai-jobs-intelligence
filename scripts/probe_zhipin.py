"""
阶段 1 探测脚本：记录 BOSS 搜索页在「未登录」状态下的真实表现。

约束（对应 docs/00-技术方案.md §1.4）：
  - 单次请求，不翻页、不循环、不批量
  - 不使用代理、不改 UA、不做频率规避
  - 只记录页面呈现了什么，不尝试绕过任何验证

用法：
  backend\\.venv\\Scripts\\python.exe scripts\\probe_zhipin.py
"""

import json
import os
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

# 大模型 + 上海（city=101020100）
TARGET = "https://www.zhipin.com/web/geek/job?query=%E5%A4%A7%E6%A8%A1%E5%9E%8B&city=101020100"

# 登录 / 验证 / 频控 的页面特征，用于判定失败类型
MARKERS = {
    "login": ["登录", "扫码登录", "手机号登录", "sign-in", "login-form", "passport"],
    "captcha": ["验证码", "captcha", "安全验证", "滑动验证", "人机验证"],
    "freq": ["访问过于频繁", "请求过于频繁", "稍后再试", "访问异常"],
}


def detect_kind(text: str, html: str) -> str:
    low_html = html.lower()
    for kind, words in MARKERS.items():
        for w in words:
            if w in text or w.lower() in low_html:
                return kind
    return "unknown"


def main() -> int:
    started = datetime.now().astimezone()
    result = {
        "probe_at": started.isoformat(),
        "target": TARGET,
        "executable": CHROME,
        "headless": True,
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROME,
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(locale="zh-CN", viewport={"width": 1440, "height": 900})
        page = ctx.new_page()

        try:
            resp = page.goto(TARGET, wait_until="domcontentloaded", timeout=40_000)
            result["http_status"] = resp.status if resp else None
            result["final_url"] = page.url
            result["title"] = page.title()
        except Exception as exc:
            result["goto_error"] = f"{type(exc).__name__}: {exc}"
            browser.close()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1

        # 等待可能的跳转稳定（单次等待，不重试）
        page.wait_for_timeout(3000)

        html = page.content()
        try:
            body_text = page.inner_text("body")
        except Exception:
            body_text = ""

        result["http_status_after_wait"] = None
        result["final_url_after_wait"] = page.url
        result["page_kind"] = detect_kind(body_text[:3000], html)
        result["body_len"] = len(html)
        result["redirected"] = page.url != TARGET

        # 职位卡片：多选择器试探，只为判断"结构化数据是否可取"
        selectors = [
            ".job-card-wrapper",
            ".job-card-box",
            "li.job-card-wrapper",
            ".job-list-item",
            ".job-list-box .job-card-wrapper",
        ]
        counts = {}
        for sel in selectors:
            try:
                counts[sel] = page.locator(sel).count()
            except Exception as exc:
                counts[sel] = f"err:{type(exc).__name__}"
        result["card_counts"] = counts

        # 首条卡片能否取到标题与链接
        first = None
        try:
            if counts.get(".job-card-wrapper", 0):
                card = page.locator(".job-card-wrapper").first
                first = {
                    "text": card.inner_text()[:200],
                    "has_link": card.locator("a").count() > 0,
                }
        except Exception as exc:
            first = {"error": f"{type(exc).__name__}: {exc}"}
        result["first_card"] = first

        result["text_head"] = body_text[:400]
        browser.close()

    result["elapsed_s"] = round((datetime.now().astimezone() - started).total_seconds(), 1)

    out_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "raw"))
    os.makedirs(out_dir, exist_ok=True)
    stamp = started.strftime("%Y%m%dT%H%M%S")
    out_path = os.path.join(out_dir, f"probe_zhipin_{stamp}.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\n[saved] {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

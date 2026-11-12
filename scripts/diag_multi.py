"""对照诊断：同一套 Playwright + 本机 Chrome，分别请求中性站点与目标站点，headless 开/关各一次。
目的：区分「平台反爬清空页面」与「Playwright 驱动 Chrome 157 渲染失败」。
共 4 次请求，全部单次，不重试。
"""

import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

CASES = [
    {"name": "neutral", "url": "https://example.com/", "headless": True},
    {"name": "neutral", "url": "https://example.com/", "headless": False},
    {"name": "zhipin", "url": "https://www.zhipin.com/", "headless": True},
    {"name": "zhipin", "url": "https://www.zhipin.com/", "headless": False},
]


def run_case(case):
    out = dict(case)
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROME,
            headless=case["headless"],
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = browser.new_page(locale="zh-CN")
        try:
            resp = page.goto(case["url"], wait_until="domcontentloaded", timeout=35_000)
            out["status"] = resp.status if resp else None
        except Exception as exc:
            out["goto_error"] = f"{type(exc).__name__}: {exc}"
        page.wait_for_timeout(2500)
        try:
            out["url_after"] = page.url
            out["title"] = page.title()
            out["body_len"] = len(page.content())
        except Exception as exc:
            out["read_error"] = f"{type(exc).__name__}: {exc}"
        browser.close()
    return out


def main():
    results = []
    for case in CASES:
        try:
            results.append(run_case(case))
        except Exception as exc:
            results.append({**case, "fatal": f"{type(exc).__name__}: {exc}"})
        print(f"[done] {case['name']} headless={case['headless']}", flush=True)
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

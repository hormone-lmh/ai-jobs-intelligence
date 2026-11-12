"""对照诊断 2：改用 Playwright 自带 Chromium，排除「Chrome 157 与 Playwright CDP 不兼容」的可能。
共 4 次请求，单次，不重试。
"""

import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright

CASES = [
    {"name": "neutral", "url": "https://example.com/", "headless": True},
    {"name": "zhipin-home", "url": "https://www.zhipin.com/", "headless": True},
    {"name": "zhipin-home", "url": "https://www.zhipin.com/", "headless": False},
    {"name": "zhipin-search", "url": "https://www.zhipin.com/web/geek/job?query=%E5%A4%A7%E6%A8%A1%E5%9E%8B", "headless": True},
]


def run_case(case):
    out = dict(case)
    with sync_playwright() as p:
        # 不指定 executable_path，使用 Playwright 自带 Chromium
        browser = p.chromium.launch(
            headless=case["headless"],
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = browser.new_page(locale="zh-CN")
        out["browser_version"] = browser.version
        try:
            resp = page.goto(case["url"], wait_until="domcontentloaded", timeout=35_000)
            out["status"] = resp.status if resp else None
        except Exception as exc:
            out["goto_error"] = f"{type(exc).__name__}: {exc}"
        page.wait_for_timeout(3000)
        try:
            out["url_after"] = page.url
            out["title"] = page.title()
            out["body_len"] = len(page.content())
            out["card_count"] = page.locator(".job-card-wrapper").count()
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

"""诊断：真实窗口（headless=False）下页面是否也被清空。单次请求，仅采样，不交互。"""

import json
import os
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
HERE = os.path.dirname(os.path.abspath(__file__))
PROFILE = os.path.abspath(os.path.join(HERE, "..", "data", "browser_profile"))
TARGET = "https://www.zhipin.com/"
WAITS = [0, 1, 2, 4, 8]


def snap(page, t):
    out = {"t_seconds": t}
    for key, fn in (
        ("url", lambda: page.url),
        ("title", lambda: page.title()),
        ("body_len", lambda: len(page.content())),
    ):
        try:
            out[key] = fn()
        except Exception as exc:
            out[key] = f"err:{type(exc).__name__}"
    return out


def main():
    res = {"diagnosed_at": datetime.now().astimezone().isoformat(), "target": TARGET}
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE,
            executable_path=CHROME,
            headless=False,
            locale="zh-CN",
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        res["before_goto"] = snap(page, -1)
        try:
            res["webdriver_before"] = page.evaluate("() => navigator.webdriver")
        except Exception:
            res["webdriver_before"] = None

        try:
            resp = page.goto(TARGET, wait_until="domcontentloaded", timeout=40_000)
            res["status"] = resp.status if resp else None
        except Exception as exc:
            res["goto_error"] = f"{type(exc).__name__}: {exc}"

        samples = []
        prev = 0
        for w in WAITS:
            page.wait_for_timeout((w - prev) * 1000)
            prev = w
            samples.append(snap(page, w))
        res["samples"] = samples

        try:
            res["ua"] = page.evaluate("() => navigator.userAgent")
            res["webdriver_after"] = page.evaluate("() => navigator.webdriver")
        except Exception:
            pass
        ctx.close()

    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

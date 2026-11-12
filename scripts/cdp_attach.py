"""验证：用 Playwright 的 connect_over_cdp 连接「已由 Chrome 自行启动」的浏览器实例。
不 launch、不加 Playwright 启动参数，只连接并读取当前页面。
"""

import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:9222"


def main():
    out = {"cdp": CDP}
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(CDP)
        except Exception as exc:
            out["connect_error"] = f"{type(exc).__name__}: {exc}"
            print(json.dumps(out, ensure_ascii=False, indent=2))
            return 1

        out["browser_version"] = browser.version
        out["contexts"] = len(browser.contexts)
        ctx = browser.contexts[0]
        pages = ctx.pages
        out["pages"] = len(pages)
        info = []
        for pg in pages:
            item = {}
            try:
                item["url"] = pg.url
                item["title"] = pg.title()
                item["body_len"] = len(pg.content())
                item["card_count"] = pg.locator(".job-card-wrapper").count()
                item["text_head"] = pg.inner_text("body")[:200].replace("\n", " ")
            except Exception as exc:
                item["error"] = f"{type(exc).__name__}: {exc}"
            info.append(item)
        out["page_info"] = info
        # 不关闭浏览器，只断开连接
        browser.close()

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

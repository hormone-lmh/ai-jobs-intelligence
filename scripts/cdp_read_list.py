"""验证：通过 CDP 连接已运行的 Chrome，读取当前列表页的职位卡片字段。
只读取，不点击、不翻页、不发新请求。
"""

import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:9222"

FIELD_SELECTORS = {
    "job_name": [".job-name", ".job-title", ".job-card-left .job-name"],
    "salary": [".salary", ".job-salary", ".job-card-right .salary"],
    "area": [".job-area", ".job-area-wrapper .job-area"],
    "company": [".company-name", ".company-info .company-name", ".company-text .name"],
    "tags": [".tag-list", ".job-card-footer .tag-list", ".job-labels"],
}


def first_text(node, selectors):
    for sel in selectors:
        try:
            loc = node.locator(sel)
            if loc.count():
                return loc.first.inner_text().strip()[:80]
        except Exception:
            continue
    return None


def main():
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP)
        ctx = browser.contexts[0]
        page = ctx.pages[0]

        # attach 会触发一次安全校验重载，等页面稳定后再读
        try:
            page.wait_for_load_state("domcontentloaded", timeout=20_000)
        except Exception:
            pass
        page.wait_for_timeout(6000)

        out = {"url": page.url, "title": page.title()}
        try:
            out["body_len"] = len(page.content())
        except Exception as exc:
            out["body_error"] = f"{type(exc).__name__}: {exc}"

        cards = page.locator(".job-card-wrapper")
        out["card_count"] = cards.count()

        samples = []
        for i in range(min(out["card_count"], 3)):
            card = cards.nth(i)
            item = {"raw": card.inner_text()[:200].replace("\n", " | ")}
            for key, sels in FIELD_SELECTORS.items():
                item[key] = first_text(card, sels)
            try:
                link = card.locator("a")
                if link.count():
                    item["href"] = link.first.get_attribute("href")
            except Exception:
                item["href"] = None
            samples.append(item)
        out["samples"] = samples

        # 页面里的分页 / 总数提示
        for key, sels in {
            "total_hint": [".job-list-box .page", ".pager", ".options-pages"],
            "filter_bar": [".search-condition", ".filter-condition"],
        }.items():
            out[key] = first_text(page, sels)

        browser.close()

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

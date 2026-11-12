"""
阶段 1 探测 2：真实窗口 + 持久 profile + 本人登录，验证列表字段与详情 JD 能否取到。

需要人工动作：脚本弹出 Chrome 窗口后，由你在窗口内完成登录（扫码或密码）。
脚本只做以下请求，全部串行、单次：
  1. 打开登录页
  2. 登录检测通过后，打开 1 个搜索页
  3. 打开 1 个详情页

不做：翻页、循环、并发、代理、UA 改写、验证码处理、频率规避。

用法：
  backend\\.venv\\Scripts\\python.exe scripts\\login_and_probe.py
"""

import json
import os
import sys
import time
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
HERE = os.path.dirname(os.path.abspath(__file__))
PROFILE = os.path.abspath(os.path.join(HERE, "..", "data", "browser_profile"))
RAW_DIR = os.path.abspath(os.path.join(HERE, "..", "data", "raw"))

LOGIN_URL = "https://www.zhipin.com/web/user/?ka=header-login"
# 大模型 / 上海
SEARCH_URL = "https://www.zhipin.com/web/geek/job?query=%E5%A4%A7%E6%A8%A1%E5%9E%8B&city=101020100"

WAIT_LOGIN_SECONDS = 480
POLL_SECONDS = 5

CARD_SELECTORS = [
    ".job-card-wrapper",
    ".job-card-box",
    "li.job-card-wrapper",
    ".job-list-item",
]


def log(msg: str) -> None:
    print(f"[probe2] {msg}", flush=True)


def login_evidence(ctx, page):
    """判断是否已登录，返回 (bool, 依据)。只读本地 cookie 与当前页面，不发请求。"""
    try:
        names = {c["name"] for c in ctx.cookies()}
    except Exception:
        names = set()
    for key in ("zp_at", "wt2", "geek_auth_token"):
        if key in names:
            return True, f"cookie:{key}"
    try:
        if "/web/user/" not in page.url:
            text = page.inner_text("body")[:600]
            if any(k in text for k in ("我的", "消息", "简历", "推荐")):
                return True, "page:nav"
    except Exception:
        pass
    return False, ""


def collect_cards(page):
    counts = {}
    for sel in CARD_SELECTORS:
        try:
            counts[sel] = page.locator(sel).count()
        except Exception as exc:
            counts[sel] = f"err:{type(exc).__name__}"
    best = max(
        (v for v in counts.values() if isinstance(v, int)), default=0
    )
    used = next((k for k, v in counts.items() if v == best and best > 0), None)
    return counts, used, best


def main() -> int:
    started = datetime.now().astimezone()
    result = {"probe_at": started.isoformat(), "profile_dir": PROFILE}
    os.makedirs(RAW_DIR, exist_ok=True)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE,
            executable_path=CHROME,
            headless=False,
            locale="zh-CN",
            viewport={"width": 1440, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        already, why = login_evidence(ctx, page)
        if already:
            log(f"检测到已登录（{why}），跳过登录等待")
            result["login"] = {"reused": True, "evidence": why}
        else:
            log("打开登录页，请在弹出的 Chrome 窗口内完成登录…")
            try:
                page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=40_000)
            except Exception as exc:
                result["login_page_error"] = f"{type(exc).__name__}: {exc}"

            deadline = time.time() + WAIT_LOGIN_SECONDS
            logged = False
            while time.time() < deadline:
                time.sleep(POLL_SECONDS)
                logged, why = login_evidence(ctx, page)
                if logged:
                    break
            if not logged:
                log("等待登录超时，未检测到登录态")
                result["login"] = {"reused": False, "ok": False, "reason": "timeout"}
                ctx.close()
                _dump(result, started, RAW_DIR)
                return 2
            log(f"登录成功（{why}），继续探测")
            result["login"] = {"reused": False, "ok": True, "evidence": why}

        # ---- 列表页 ----
        log("请求搜索页（1 次）")
        try:
            resp = page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=40_000)
            result["list_status"] = resp.status if resp else None
        except Exception as exc:
            result["list_error"] = f"{type(exc).__name__}: {exc}"
            ctx.close()
            _dump(result, started, RAW_DIR)
            return 3

        page.wait_for_timeout(4000)
        result["list_url_after_wait"] = page.url
        result["list_title"] = page.title()
        counts, used, best = collect_cards(page)
        result["card_counts"] = counts
        result["card_selector_used"] = used
        result["card_count"] = best

        cards = []
        if best:
            try:
                node = page.locator(used)
                for i in range(min(best, 3)):
                    card = node.nth(i)
                    item = {"raw_text": card.inner_text()[:300]}
                    link = card.locator("a")
                    if link.count():
                        item["href"] = link.first.get_attribute("href")
                    cards.append(item)
            except Exception as exc:
                result["card_parse_error"] = f"{type(exc).__name__}: {exc}"
        result["cards"] = cards

        # ---- 详情页（仅 1 条）----
        if cards and cards[0].get("href"):
            href = cards[0]["href"]
            if href.startswith("/"):
                href = "https://www.zhipin.com" + href
            log("请求详情页（1 次）")
            try:
                dresp = page.goto(href, wait_until="domcontentloaded", timeout=40_000)
                result["detail_status"] = dresp.status if dresp else None
                page.wait_for_timeout(3000)
                result["detail_url"] = page.url
                result["detail_title"] = page.title()

                jd = {}
                for sel in (".job-sec-text", ".job-detail-section", ".job-sec", "section.job-sec"):
                    n = page.locator(sel).count()
                    jd[sel] = n
                result["jd_selectors"] = jd

                texts = []
                if page.locator(".job-sec-text").count():
                    for i in range(page.locator(".job-sec-text").count()):
                        try:
                            texts.append(page.locator(".job-sec-text").nth(i).inner_text()[:1500])
                        except Exception:
                            pass
                result["jd_texts"] = texts
                result["jd_combined_len"] = sum(len(t) for t in texts)

                # 详情页头部字段
                head = {}
                for sel, key in [
                    (".job-banner .name", "title"),
                    (".job-banner .company-info .name", "company"),
                    (".job-banner .salary", "salary"),
                    (".job-banner .text-city", "city"),
                    (".job-banner .text-experiece", "experience"),
                    (".job-banner .text-degree", "degree"),
                ]:
                    try:
                        head[key] = page.locator(sel).first.inner_text()[:120] if page.locator(sel).count() else None
                    except Exception:
                        head[key] = None
                result["detail_head"] = head
            except Exception as exc:
                result["detail_error"] = f"{type(exc).__name__}: {exc}"

        ctx.close()

    _dump(result, started, RAW_DIR)
    return 0


def _dump(result, started, raw_dir):
    result["elapsed_s"] = round((datetime.now().astimezone() - started).total_seconds(), 1)
    stamp = started.strftime("%Y%m%dT%H%M%S")
    path = os.path.join(raw_dir, f"probe_zhipin_login_{stamp}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\n[saved] {path}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())

"""Headless Chromium (Playwright) til karrieresider, der først bygger joblisten i browseren.

Én browser deles af hele kørslen. Kun tilgængelig hvor Playwright er installeret (GitHub Actions).
"""
from __future__ import annotations

import atexit
import json
import re
import time

_pw = None
_browser = None
_ctx = None

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")

COOKIE_BUTTONS = [
    "Kun nødvendige", "Afvis alle", "Afvis", "Reject all", "Reject All", "Decline", "Only necessary",
    "Accepter kun nødvendige", "Tillad kun nødvendige", "Use necessary cookies only", "Necessary only",
]
MORE_BUTTONS = ["Vis flere", "Indlæs flere", "Se flere", "Load more", "Show more", "View more", "More jobs"]


def _ensure():
    global _pw, _browser, _ctx
    if _ctx is None:
        from playwright.sync_api import sync_playwright
        _pw = sync_playwright().start()
        _browser = _pw.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        _ctx = _browser.new_context(user_agent=UA, locale="da-DK", viewport={"width": 1366, "height": 900})
        atexit.register(close)
    return _ctx


def close():
    global _pw, _browser, _ctx
    try:
        if _browser:
            _browser.close()
        if _pw:
            _pw.stop()
    except Exception:
        pass
    _pw = _browser = _ctx = None


def _click_text(page, labels, timeout=1200) -> bool:
    for lab in labels:
        try:
            loc = page.get_by_role("button", name=re.compile(rf"^\s*{re.escape(lab)}\s*$", re.I))
            if loc.count():
                loc.first.click(timeout=timeout)
                return True
        except Exception:
            continue
    return False


def render(url: str, wait_ms: int = 2500, scroll: int = 4, more_clicks: int = 3, capture_json: bool = False,
           wait_for: str | None = None, timeout: int = 45000) -> dict:
    """Åbner siden og returnerer {url, title, html, text, links:[(tekst, href)], json:[(url, body)]}."""
    ctx = _ensure()
    page = ctx.new_page()
    captured = []
    if capture_json:
        def on_resp(r):
            try:
                ct = r.headers.get("content-type", "")
                if "json" in ct and r.request.resource_type in ("xhr", "fetch"):
                    captured.append((r.url, r.text()[:20000]))
            except Exception:
                pass
        page.on("response", on_resp)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        _click_text(page, COOKIE_BUTTONS)
        if wait_for:
            try:
                page.wait_for_selector(wait_for, timeout=15000)
            except Exception:
                pass
        page.wait_for_timeout(wait_ms)
        for _ in range(scroll):
            page.mouse.wheel(0, 4000)
            page.wait_for_timeout(600)
        for _ in range(more_clicks):
            if not _click_text(page, MORE_BUTTONS):
                break
            page.wait_for_timeout(1500)
        links = page.eval_on_selector_all(
            "a[href]", "els => els.map(e => [(e.innerText || e.getAttribute('aria-label') || '').trim(), e.href])")
        out = {"url": page.url, "title": page.title(), "html": page.content(),
               "text": page.inner_text("body")[:200000], "links": links, "json": captured}
        return out
    finally:
        page.close()
        time.sleep(0.5)


def jsonld(html: str) -> dict | None:
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            data = json.loads(m.group(1))
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for it in list(items):
            if isinstance(it, dict) and "@graph" in it:
                items.extend(it["@graph"])
        for it in items:
            if isinstance(it, dict) and "JobPosting" in str(it.get("@type")):
                return it
    return None

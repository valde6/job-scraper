"""Emply (kunde.career.emply.com) – bruges af mange kommuner, foreninger, a-kasser og advokatfirmaer.

Config:
  url: https://aeldresagen.career.emply.com        (eller kundens eget domæne, fx https://job.frederiksberg.dk)
  path: /ledige-stillinger                         (valgfri; standard)

Joblisten hentes fra karrieresidens eget JSON-kald (samme som siden selv bruger):
  1. GET listesiden → `sectionId` og sprog (`languageKey`) står i sidens script.
  2. POST /api/integration/vacancy/get-page med {sectionId, count, offset, ...} → {"vacancies": [...], "count": n}
Hvert opslag har titel, frist, afdeling, sted og selve teksten (translations[].content), så detaljesiden skal
ikke hentes. Opslagets adresse er /ad/<titleAsUrl>/<shortId>.
Findes sectionId ikke (anderledes side), falder vi tilbage til browseren.
"""
import re

from ..common import Job, clean, get, html_to_md, is_denmark, post, student_fit, topic_tags, reject
from . import browser as browser_adapter

LINK_PATTERN = r"/ad/[^/?#]+/[a-z0-9]{5,8}"
PAGE = 100
MAX_PAGES = 10
_SECTION_RE = re.compile(r"sectionId\s*:\s*'([0-9a-f-]{36})'")
_LANG_RE = re.compile(r"languageKey\s*=\s*'([^']+)'")
_ADLINK_RE = re.compile(r"adLink\s*=\s*'([^']*)/ad/'")        # fx '/da/ad/' på sider med flere sprog


def _browser(cfg, base):
    return browser_adapter.scrape({
        "name": cfg["name"],
        "urls": [base + cfg.get("path", "/ledige-stillinger")],
        "link_pattern": LINK_PATTERN,
        "dk_only": cfg.get("dk_only", True),
        "detail": cfg.get("detail", "browser"),
        "more_clicks": 5,
    })


def vacancies(base: str, path: str) -> tuple[list[dict], str] | None:
    """(alle opslag, sti-præfiks for opslag) fra Emply-sidens JSON-kald, eller None hvis siden ikke har det."""
    html = get(base + path).text
    m = _SECTION_RE.search(html)
    if not m:
        return None
    prefix = (_ADLINK_RE.search(html) or [None, ""])[1]
    lang = (_LANG_RE.search(html) or [None, "da-DK"])[1]
    out = []
    for page in range(MAX_PAGES):
        body = {"count": PAGE, "filters": [], "langCode": lang, "offset": page * PAGE, "searchText": "",
                "sectionId": m.group(1), "sortByProjectDataId": "", "sortAscending": False, "light": False,
                "isJobAgent": False, "siteId": None}
        data = post(base + "/api/integration/vacancy/get-page", json=body).json()
        batch = (data or {}).get("vacancies") or []
        out.extend(batch)
        if len(batch) < PAGE:
            break
    return out, prefix


def _text(v: dict) -> tuple[str, str]:
    tr = v.get("translations") or []
    t = tr[0] if tr else {}
    return clean(t.get("title") or v.get("title")), t.get("content") or ""


def scrape(cfg):
    base = cfg["url"].rstrip("/")
    path = cfg.get("path", "/ledige-stillinger")
    found = vacancies(base, path)
    if found is None:
        return _browser(cfg, base)
    items, prefix = found
    listed, jobs = 0, []
    for v in items:
        listed += 1
        title, content_html = _text(v)
        if not title or v.get("talentPool"):
            continue
        content = html_to_md(content_html)
        fit = student_fit(title, content)
        if not fit or (fit != "sikker" and not topic_tags(title, content[:3000])):
            reject(cfg["name"], title, "ikke studiejob")
            continue
        loc = clean(v.get("location"))
        if loc and not cfg.get("dk_only", True) and not is_denmark(loc):
            continue
        slug, short = v.get("titleAsUrl") or "opslag", v.get("shortId")
        # Samme adresse som siden selv bygger (og som browser-adapteren gemte før), så job-id'erne ikke skifter.
        url = v.get("directLink") or (f"{base}{prefix}/ad/{slug}/{short}" if short else base + path)
        apply = v.get("applyLink") or v.get("externalCseApplyLink") or url
        jobs.append(Job(
            company=cfg["name"], title=title, url=url, apply_url=apply, location=loc or "Danmark",
            posted=(v.get("published") or v.get("created") or "")[:10],
            deadline=(v.get("deadline") or "")[:10],
            description_md=content, source="emply", external_id=url, fit=fit,
        ))
    return listed, jobs

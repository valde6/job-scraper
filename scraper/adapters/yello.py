"""Yello (yello.co) – bruges til "early careers" (studiejob, praktik, graduate), fx EY.

Config:
  url: https://eyglobal.yello.co/job_boards/c1riT--B2O-KySgYWsZO1Q
  queries: ["Denmark"]          # fritekst-søgning; matcher også lokation. Default: Denmark, Copenhagen, København
Søgningen /search?query=… svarer med JSON {"html": "<li …>", "more_requisitions": bool}.
"""
from datetime import date
from urllib.parse import urljoin

from ..common import Job, clean, get, html_to_md, jsonld_jobposting, jsonld_location, soup, student_fit, find_deadline

QUERIES = ["Denmark", "Copenhagen", "København"]


def _search(board: str, query: str, page: int):
    r = get(f"{board}/search", params={"query": query, "page_number": page},
            headers={"Accept": "application/json, text/javascript, */*; q=0.01", "X-Requested-With": "XMLHttpRequest"})
    try:
        data = r.json()
    except ValueError:
        return [], False
    s = soup(data.get("html") or "")
    rows = []
    for a in s.select("a.search-results__req_title, a[href*='/jobs/']"):
        rows.append((clean(a.get_text()), urljoin(board, a.get("href", ""))))
    return rows, bool(data.get("more_requisitions"))


def _detail(url: str):
    html = get(url).text
    jp = jsonld_jobposting(html) or {}
    s = soup(html)
    for bad in s.select("nav, header, footer, script, style, form, aside, noscript"):
        bad.decompose()
    main = (s.select_one(".job-description, [class*=description], .requisition-description, main, article") or s.body)
    md = html_to_md(jp["description"]) if jp.get("description") else html_to_md(str(main) if main else "")
    return jp, md


def scrape(cfg):
    board = cfg["url"].split("?")[0].rstrip("/")
    seen, listed, jobs = set(), 0, []
    for q in cfg.get("queries", QUERIES):
        for page in range(1, 6):
            rows, more = _search(board, q, page)
            new = 0
            for title, href in rows:
                key = href.split("?")[0]
                if not title or key in seen:
                    continue
                seen.add(key)
                new += 1
                listed += 1
                fit = student_fit(title, "")
                if not fit:
                    continue
                try:
                    jp, md = _detail(href)
                except Exception:  # noqa: BLE001
                    jp, md = {}, ""
                loc = jsonld_location(jp) if jp else ""
                jobs.append(Job(
                    company=cfg["name"], title=title, url=href, apply_url=href,
                    location=loc or ("Danmark" if q == "Denmark" else q),
                    posted=(jp.get("datePosted") or "")[:10],
                    deadline=(jp.get("validThrough") or "")[:10] or (find_deadline(md, date.today().year) or ""),
                    description_md=md, source="yello", external_id=key.rsplit("/", 1)[-1], fit=fit,
                ))
            if not more or new == 0:
                break
    return listed, jobs

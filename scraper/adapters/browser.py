"""Browser-kilde: karrieresider, der først viser joblisten, når JavaScript har kørt.

Config (companies.yaml):
  type: browser
  urls: ["https://.../search?q={q}&location=Denmark"]   # {q} erstattes af hvert søgeord
  search_terms: ["student", "studentermedhjælper"]       # valgfri (default nedenfor)
  link_pattern: "/job/|/jobs/\\d+"                       # regex for links til enkelte opslag
  dk_only: true                                          # siden viser kun danske job (spring lokationstjek over)
  detail: browser | http                                 # hvordan opslaget hentes (default browser)
"""
import re
from datetime import date
from urllib.parse import quote, urldefrag

from .. import browser as B
from ..common import (Job, clean, get, html_to_md, soup, is_denmark, student_fit, topic_tags,
                      jsonld_location, find_deadline)

TERMS = ["student", "studentermedhjælper"]


def _title_from_anchor(txt: str) -> str:
    lines = [clean(x) for x in (txt or "").split("\n") if clean(x)]
    return lines[0] if lines else ""


def _detail(url: str, how: str):
    if how == "http":
        html = get(url).text
        s = soup(html)
        for bad in s.select("nav, header, footer, script, style, form, aside"):
            bad.decompose()
        main = s.select_one("main, article, [role=main]") or s.body
        return html, html_to_md(str(main) if main else "")
    r = B.render(url, wait_ms=1500, scroll=1, more_clicks=0)
    s = soup(r["html"])
    for bad in s.select("nav, header, footer, script, style, form, aside, noscript"):
        bad.decompose()
    main = s.select_one("main, article, [role=main], #content, .job-description, [class*=description]") or s.body
    md = html_to_md(str(main)) if main else ""
    if len(md) < 300:
        md = r["text"][:15000]
    return r["html"], md


def scrape(cfg):
    pat = re.compile(cfg["link_pattern"], re.I)
    terms = cfg.get("search_terms", TERMS)
    how = cfg.get("detail", "browser")
    seen, listed, jobs = set(), 0, []
    urls = []
    for u in cfg["urls"]:
        urls += [u.replace("{q}", quote(t)) for t in terms] if "{q}" in u else [u]
    for u in urls:
        page = B.render(u, wait_for=cfg.get("wait_for"), more_clicks=cfg.get("more_clicks", 3))
        for txt, href in page["links"]:
            href = urldefrag(href)[0]
            if not href.startswith("http") or href in seen or not pat.search(href):
                continue
            title = _title_from_anchor(txt)
            if len(title) < 5:
                continue
            seen.add(href)
            listed += 1
            fit = student_fit(title, "")
            if fit != "sikker":
                continue   # browser-sider er dyre: kun oplagte studiejob (titel) hentes i detaljer
            try:
                html, md = _detail(href, how)
            except Exception:
                continue
            jp = B.jsonld(html) or {}
            loc = jsonld_location(jp) if jp else ""
            if not cfg.get("dk_only") and not is_denmark(loc, txt, md[:1500]):
                continue
            jobs.append(Job(
                company=cfg["name"], title=title, url=href, apply_url=href,
                location=loc or ("Danmark" if cfg.get("dk_only") else clean(txt.replace(title, ""))[:80]),
                posted=(jp.get("datePosted") or "")[:10],
                deadline=(jp.get("validThrough") or "")[:10] or (find_deadline(md, date.today().year) or ""),
                description_md=html_to_md(jp["description"]) if jp.get("description") else md,
                source="browser", external_id=href, fit=fit,
            ))
    return listed, jobs

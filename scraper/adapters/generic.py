"""Generisk HTML-adapter til karrieresider, der er server-renderede.

Config:
  list_urls: [https://..../ledige-stillinger]   side(r) med links til opslag
  link_pattern: "/job/|/stilling/"              regex på links til opslag
  dk_only: true                                 virksomheden har kun danske job (så springes lokationstjek over)
Detaljesiden læses via schema.org JobPosting (JSON-LD) og ellers sidens hovedtekst.
"""
import re
from datetime import date
from urllib.parse import urljoin, urldefrag

from ..common import Job, get, soup, clean, html_to_md, is_denmark, is_student, jsonld_jobposting, jsonld_location, find_deadline


def _main_html(s):
    for sel in ("[itemprop=description]", "article", "main", "[role=main]", "#content", ".content", "body"):
        el = s.select_one(sel)
        if el and len(el.get_text(strip=True)) > 200:
            for bad in el.select("nav, header, footer, script, style, form, aside"):
                bad.decompose()
            return str(el)
    return ""


def detail(company, title, href, dk_only, list_loc=""):
    html = get(href).text
    jp = jsonld_jobposting(html) or {}
    s = soup(html)
    title = title or clean(jp.get("title")) or clean((s.find("h1") or s.new_tag("x")).get_text())
    loc = list_loc or jsonld_location(jp)
    if not dk_only and not is_denmark(loc):
        return None
    desc_md = html_to_md(jp.get("description")) if jp.get("description") else html_to_md(_main_html(s))
    apply = None
    for a in s.find_all("a", href=True):
        txt = clean(a.get_text()).lower()
        if any(w in txt for w in ("søg stilling", "søg jobbet", "ansøg", "apply", "søg nu", "send ansøgning")):
            apply = urljoin(href, a["href"])
            break
    return Job(company=company, title=title, url=href, apply_url=apply or href, location=loc or "Danmark",
               posted=(jp.get("datePosted") or "")[:10],
               deadline=(jp.get("validThrough") or "")[:10] or (find_deadline(desc_md, date.today().year) or ""),
               description_md=desc_md, source="generic", external_id=href)


def scrape(cfg):
    pat = re.compile(cfg.get("link_pattern", r"job|stilling|vacanc|position|career"), re.I)
    dk_only = cfg.get("dk_only", False)
    seen, listed, jobs = set(), 0, []
    for lu in cfg["list_urls"]:
        s = soup(get(lu).text)
        for a in s.find_all("a", href=True):
            href = urldefrag(urljoin(lu, a["href"]))[0]
            if href in seen or href.rstrip("/") == lu.rstrip("/") or not pat.search(href):
                continue
            title = clean(a.get_text())
            if len(title) < 6:
                continue
            seen.add(href)
            listed += 1
            if not is_student(title):
                continue
            j = detail(cfg["name"], title, href, dk_only)
            if j:
                jobs.append(j)
    return listed, jobs

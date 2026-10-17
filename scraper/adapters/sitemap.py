"""Generisk adapter: sitemap.xml + strukturerede jobdata (schema.org JobPosting).

Karrieresider vil gerne findes i Google for Jobs og udgiver derfor næsten altid en sitemap med alle opslag og
schema.org-`JobPosting` (JSON-LD eller microdata) på hver jobside. Begge dele er lavet til maskiner og ændres
sjældent, så adapteren er uafhængig af sidernes layout, søgefelter og knapper.

Virker fx for SAP SuccessFactors Career Site Builder (careers.coloplast.com, careers.carlsberg.com, careers.tryg.com,
dsb.jobs.hr.cloud.sap), Radancy/TalentBrew (careers.loreal.com) og mange egne CMS-sider.

Config:
  url: https://careers.coloplast.com        karrieresidens rod (sitemap findes via robots.txt eller /sitemap.xml)
  sitemap: https://…/sitemap.xml             (valgfri) eller en liste
  job_pattern: "/job/"                       (valgfri) regex for jobsiders adresse
  url_filter: "copenhagen|student"           (valgfri) regex – kun adresser, der matcher, hentes. Standard: adressen
                                             nævner et studieord eller et sted på Sjælland/i Danmark (titel og by står
                                             typisk i adressen), så vi ikke henter hundredvis af udenlandske opslag.
  max_details: 150                           (valgfri) loft over antal jobsider pr. kørsel
  dk_only: true                              (standard)
"""
import html as htmllib
import re
from urllib.parse import unquote, urljoin

from ..common import (CPH_PLACES, DK_PLACES, HARD_EXCLUDE_RE, RETAIL_RE, SJ_PLACES, Job, clean, extract_posting, get, html_to_md, is_denmark,
                      reject, robots_allows, robots_sitemaps, student_fit, topic_tags)

JOB_PATTERN = r"/job/|/jobs?/[^/?#]+/\d{3,}|/JobDetail/|/FolderDetail/|/ad/[^/]+/[a-z0-9]{5,8}|/vacanc|/stilling|/position/"
STUDY_URL_RE = re.compile(r"student|studerende|studie|intern|praktik|graduate|trainee|deltid|part-?time|working-student|"
                          r"thesis|speciale", re.I)
_PLACE_TOKENS = sorted({p.strip(" ,-") for p in CPH_PLACES + SJ_PLACES + DK_PLACES if len(p.strip(" ,-")) >= 4}, key=len)
_PLACE_RE = re.compile("|".join(re.escape(p).replace(r"\ ", "[-_ ]") for p in _PLACE_TOKENS), re.I)
MAX_SITEMAPS = 25
MAX_DETAILS = 150


def _locs(xml: str) -> list[str]:
    return [htmllib.unescape(u).strip() for u in re.findall(r"<loc>\s*([^<]+?)\s*</loc>", xml)]


def sitemap_urls(base: str, explicit=None) -> list[str]:
    """Alle adresser i sitemap(s), inkl. sitemap-indeks (ét niveau ned)."""
    todo = [explicit] if isinstance(explicit, str) else list(explicit or [])
    if not todo:
        todo = robots_sitemaps(base) or [base.rstrip("/") + "/sitemap.xml"]
    seen, out = set(), []
    while todo and len(seen) < MAX_SITEMAPS:
        sm = urljoin(base + "/", todo.pop(0))
        if sm in seen:
            continue
        seen.add(sm)
        try:
            xml = get(sm).text
        except Exception:  # noqa: BLE001 – én sitemap, der fejler, må ikke vælte resten
            continue
        locs = _locs(xml)
        if re.search(r"<sitemapindex", xml[:2000], re.I):
            todo.extend(locs)
        else:
            out.extend(locs)
    return list(dict.fromkeys(out))


# Sprogudgaver i adressen (/de-de/, /fr_FR/): kun dansk og engelsk hentes – resten er samme opslag på andre sprog
# eller udenlandske opslag.
_LOCALE_RE = re.compile(r"/([a-z]{2})[-_][a-zA-Z]{2}(?:/|$)")
_FOREIGN_RE = re.compile(r"werkstudent|praktikum|ausbildung|stagiaire|\bstage\b|alternance|becario|tirocinio|stagiair|"
                         r"\blia\b|praktikanter\s+till|sommarjobb|\bm/w/d\b|\(mwd\)", re.I)


def candidates(urls: list[str], job_pattern: str, url_filter: str | None) -> list[str]:
    """Jobsider, der er værd at hente, sorteret: adresser med et dansk sted først, derefter adresser med et studieord.
    Store sitemaps (DSV 2.000+, Capgemini 6.000+) har mest udenlandske opslag, og loftet `max_details` må ikke
    bruges op på dem."""
    jp = re.compile(job_pattern, re.I)
    flt = re.compile(url_filter, re.I) if url_filter else None
    first, second = [], []
    for u in urls:
        if not jp.search(u):
            continue
        raw = unquote(u)
        text = raw.replace("-", " ").replace("_", " ")
        loc = _LOCALE_RE.search(raw)
        if loc and loc.group(1).lower() not in ("da", "en"):
            continue
        if flt:
            if flt.search(raw):
                first.append(u)
            continue
        if _FOREIGN_RE.search(text) or RETAIL_RE.search(text) or HARD_EXCLUDE_RE.search(text):
            continue
        if _PLACE_RE.search(text):
            first.append(u)
        elif STUDY_URL_RE.search(text):
            second.append(u)
    return first + second


def url_place(url: str) -> str:
    """Bynavn fra adressen, når siden ikke selv angiver et sted (SuccessFactors: /job/Humlebæk-Student-…/123/)."""
    m = _PLACE_RE.search(unquote(url).replace("-", " ").replace("_", " "))
    return m.group(0).title() if m else ""


def dk(loc: str) -> bool:
    l = (loc or "").lower().replace("new zealand", "")
    return is_denmark(l) or bool(_PLACE_RE.search(l))


def _external_id(url: str) -> str:
    m = re.search(r"/(\d{4,})/?(?:[?#].*)?$", url) or re.search(r"/([A-Za-z0-9]{5,})/?(?:[?#].*)?$", url)
    return m.group(1) if m else url


def scrape(cfg):
    base = cfg["url"].rstrip("/")
    urls = sitemap_urls(base, cfg.get("sitemap"))
    jobs_urls = [u for u in urls if re.search(cfg.get("job_pattern", JOB_PATTERN), u, re.I)]
    cands = candidates(urls, cfg.get("job_pattern", JOB_PATTERN), cfg.get("url_filter"))
    listed, jobs = len(jobs_urls), []
    for url in cands[: int(cfg.get("max_details", MAX_DETAILS))]:
        if not robots_allows(url):
            reject(cfg["name"], url, "robots.txt forbyder", url)
            continue
        try:
            p = extract_posting(get(url).text)
        except Exception:  # noqa: BLE001 – ét opslag, der fejler (404, timeout), må ikke vælte kilden
            continue
        title = clean(p["title"]) or clean(unquote(url.rstrip("/").split("/")[-2]).replace("-", " "))
        desc = html_to_md(p["description_html"])
        loc = clean(p["location"]) or url_place(url)
        if cfg.get("dk_only", True) and not dk(loc):
            reject(cfg["name"], title, f"uden for Danmark ({loc[:40]})", url)
            continue
        fit = student_fit(title, desc + " " + p.get("employment_type", ""))
        if not fit or (fit != "sikker" and not topic_tags(title, desc[:3000])):
            reject(cfg["name"], title, "ikke studiejob", url)
            continue
        jobs.append(Job(company=cfg["name"], title=title, url=url, location=loc or "Danmark",
                        posted=p["posted"], deadline=p["deadline"], description_md=desc,
                        source="sitemap", external_id=_external_id(url), fit=fit))
    return listed, jobs

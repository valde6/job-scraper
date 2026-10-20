"""Generisk HTML-adapter til karrieresider, der er server-renderede.

Config:
  list_urls: [https://..../ledige-stillinger]   side(r) med links til opslag
  link_pattern: "/job/|/stilling/"              regex på links til opslag
  dk_only: true                                 virksomheden har kun danske job (så springes lokationstjek over)
  pages: {param: page, start: 0, max: 30}       (valgfri) bladr i listen med ?page=N, til en side ikke giver nye links
  title_prefix: "^Om stillingen\\s+"            (valgfri) regex der fjernes fra link-teksten (fx CBS)
  title_from: detail                            (valgfri) titlen tages fra opslaget (JSON-LD/h1), ikke link-teksten –
                                                til lister, hvor linket hedder "Læs mere" (Mazanti) eller indeholder
                                                frist og by (Bech-Bruun). Hver jobside hentes, så kun til små lister.
Detaljesiden læses via schema.org JobPosting (JSON-LD) og ellers sidens hovedtekst.
"""
import re
from datetime import date
from urllib.parse import urljoin, urldefrag

from ..common import Job, get, soup, clean, html_to_md, is_denmark, is_student, jsonld_jobposting, jsonld_location, find_deadline, reject


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


def _list_pages(cfg):
    """Listesiderne: list_urls, og – med `pages` – hver af dem med ?page=start, start+1, …"""
    pg = cfg.get("pages")
    for lu in cfg["list_urls"]:
        if not pg:
            yield lu, None
            continue
        sep = "&" if "?" in lu else "?"
        for n in range(pg.get("start", 0), pg.get("start", 0) + pg.get("max", 30)):
            yield f"{lu}{sep}{pg.get('param', 'page')}={n}", lu


def clean_title(raw: str, prefix: str | None = None) -> str:
    t = clean((raw or "").replace("\u00ad", ""))       # bløde bindestreger (CBS)
    if prefix:
        t = clean(re.sub(prefix, "", t, flags=re.I))
    return t[7:] if t.lower().startswith("se job ") else t


def scrape(cfg):
    pat = re.compile(cfg.get("link_pattern", r"job|stilling|vacanc|position|career"), re.I)
    dk_only = cfg.get("dk_only", False)
    seen, listed, jobs = set(), 0, []
    done = set()                                    # listesider, hvor vi har bladret til enden
    for lu, base in _list_pages(cfg):
        if base in done:
            continue
        try:
            s = soup(get(lu).text)
        except Exception:  # noqa: BLE001
            if base and listed:                     # en senere side i bladringen fejler → stop bladringen
                done.add(base)
                continue
            raise                                   # første liste-side fejler → kilden er reelt nede
        new_links = 0
        for a in s.find_all("a", href=True):
            href = urldefrag(urljoin(lu, a["href"]))[0]
            if href in seen or href.rstrip("/") == lu.rstrip("/") or not pat.search(href):
                continue
            title = clean_title(a.get_text(), cfg.get("title_prefix"))
            from_detail = cfg.get("title_from") == "detail"
            if len(title) < 6 and not from_detail:
                continue
            seen.add(href)
            listed += 1
            new_links += 1
            if not from_detail and not is_student(title):
                reject(cfg["name"], title, "ikke studiejob (titel)", href)
                continue
            try:
                j = detail(cfg["name"], "" if from_detail else title, href, dk_only)
            except Exception:  # noqa: BLE001 – ét opslag, der fejler (fx 404), må ikke vælte kilden (CBS 17/10)
                reject(cfg["name"], title, "jobsiden kunne ikke hentes", href)
                continue
            if j and from_detail and not is_student(j.title):
                reject(cfg["name"], j.title, "ikke studiejob (titel)", href)
                continue
            if j:
                jobs.append(j)
        if base and new_links == 0:
            done.add(base)                          # sidste side nået (eller samme side igen)
    return listed, jobs

"""Linkkontrol efter hver Jobradar-kørsel (2/11).

Valdemars stikprøver 2/11 endte ofte i døde eller tomme sider: Jyske Banks opslag sagde "Jobopslaget blev ikke fundet",
Arlas opslag sendte videre til forsiden, og Nordnets karriereside gav 404. Årsagen var, at et job forbliver aktivt, så
længe kilden ikke svarer (Jyske Bank: 403 i 9 kørsler), og at ingen tjekkede, om linkene i appen virker.

Her hentes hvert aktivt jobs opslag og hver arbejdsgivers karriereside én gang pr. kørsel:
  - "dead"    – 404/410, viderestilling til en fejlside eller væk fra opslaget, eller siden siger, at opslaget er væk
  - "ok"      – siden svarede 2xx og ligner ikke en fejlside
  - "unknown" – timeout, 403/429/5xx, robots.txt forbyder, eller siden er en JavaScript-app uden indhold i HTML'en.
                Bruges aldrig til at lukke et job (en bot-mur må ikke tømme en arbejdsgiver).
Resultatet skrives til data/jobradar/linkcheck.json. jobs.json får ingen nye felter.
"""
from __future__ import annotations

import re
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .common import robots_allows

UA = "Mozilla/5.0 (compatible; StudieradarLinkCheck/1.0; +https://studieradar.dk)"
TIMEOUT = 15
PAUSE = 0.7                 # sekunder mellem kald til samme vært
WORKERS = 8                 # forskellige værter tjekkes samtidig

# Tekst, der betyder, at opslaget/siden ikke findes (titel, h1 og starten af hovedteksten).
DEAD_TEXT_RE = re.compile(
    r"page\s+(?:was\s+)?not\s+found|siden\s+(?:blev\s+ikke\s+fundet|findes\s+ikke|kunne\s+ikke\s+findes)|"
    r"(?:job)?opslaget\s+(?:blev\s+ikke\s+fundet|findes\s+ikke|er\s+(?:udløbet|lukket|ikke\s+længere))|"
    r"stillingen\s+(?:er\s+(?:lukket|besat|udløbet|ikke\s+længere)|findes\s+ikke)|annoncen\s+er\s+(?:udløbet|lukket)|"
    r"(?:job|position|posting|vacancy|requisition)\s+(?:is\s+)?no\s+longer\s+(?:available|open|active|accepting)|"
    r"no\s+longer\s+accepting\s+applications|this\s+(?:job|position|vacancy)\s+(?:has\s+)?(?:expired|been\s+filled|is\s+closed)|"
    r"job\s+not\s+found|the\s+job\s+you\s+are\s+looking\s+for|ikke\s+længere\s+(?:aktiv|ledig|tilgængelig|muligt\s+at\s+søge)",
    re.I,
)
TITLE_404_RE = re.compile(r"\b404\b|not\s+found|ikke\s+fundet", re.I)      # kun i titel/overskrift, ikke i brødteksten
ERROR_PATH_RE = re.compile(r"/(?:404|not-?found|page-?not-?found|error|fejl)(?:[/?.#]|$)", re.I)
# Systemer, hvis opslag er JavaScript-apps (HTML'en er en tom skal). Deres job kommer fra systemets API, som kun
# viser åbne opslag, så sidens tekst siger intet. HTTP-status og viderestilling tjekkes stadig.
SPA_HOSTS = ("oraclecloud.com", "myworkdayjobs.com", "successfactors.eu", "successfactors.com", "smartrecruiters.com",
             "eightfold.ai", "yello.co", "phenompeople.com", "avature.net")


def _id_tokens(url: str) -> list[str]:
    """Det, der identificerer opslaget i URL'en: tal på 4+ cifre og sidste sti-led."""
    p = urlparse(url)
    toks = re.findall(r"\d{4,}", p.path + "?" + p.query)
    last = [x for x in p.path.split("/") if x]
    if last and len(last[-1]) >= 6:
        toks.append(last[-1].lower())
    return toks


def _depth(url: str) -> int:
    return len([x for x in urlparse(url).path.split("/") if x])


def classify(url: str, status: int, final_url: str, html: str, kind: str = "job") -> tuple[str, str]:
    """(dom, årsag) ud fra et HTTP-svar. kind = "job" (et opslag) eller "page" (en karriereside)."""
    if status in (404, 410):
        return "dead", f"HTTP {status}"
    if status >= 400:
        return "unknown", f"HTTP {status}"
    if final_url and ERROR_PATH_RE.search(urlparse(final_url).path) and not ERROR_PATH_RE.search(urlparse(url).path):
        return "dead", f"viderestillet til fejlside ({final_url[:80]})"
    if kind == "job" and final_url and final_url.rstrip("/") != url.rstrip("/"):
        toks = _id_tokens(url)
        lost = toks and not any(t in final_url.lower() for t in toks)
        if lost and _depth(final_url) < _depth(url) - 1:
            return "dead", f"viderestillet væk fra opslaget ({final_url[:80]})"     # Arla: /global/en/job/111024 → /gb/en
    s = BeautifulSoup(html or "", "lxml")
    for bad in s.select("script, style, noscript, nav, footer, header"):
        bad.decompose()
    title = (s.title.get_text(" ", strip=True) if s.title else "")[:200]
    h1 = " ".join(h.get_text(" ", strip=True) for h in s.find_all("h1")[:2])[:200]
    main = s.select_one("main, article, [role=main]") or s.body or s
    body = re.sub(r"\s+", " ", main.get_text(" ", strip=True))[:1500]
    for where, txt in (("titel", title), ("overskrift", h1), ("tekst", body)):
        m = DEAD_TEXT_RE.search(txt) or (TITLE_404_RE.search(txt) if where != "tekst" else None)
        if m:
            return "dead", f"{where}: {m.group(0)[:60]}"
    host = urlparse(final_url or url).netloc.lower()
    if any(host == h or host.endswith("." + h) for h in SPA_HOSTS):
        return "ok", "JavaScript-side (kun status tjekket)"
    if kind == "job" and len(body) < 80 and not title:
        return "unknown", "tom side"
    return "ok", ""


def fetch(url: str) -> tuple[int, str, str]:
    r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "da,en;q=0.8"}, timeout=TIMEOUT,
                     allow_redirects=True)
    return r.status_code, r.url, r.text[:400_000] if "html" in r.headers.get("content-type", "html") else ""


def check(url: str, kind: str = "job", fetcher=fetch, robots=robots_allows) -> tuple[str, str]:
    if not url or not url.startswith("http"):
        return "unknown", "intet link"
    try:
        if not robots(url):
            return "unknown", "robots.txt forbyder"
    except Exception:  # noqa: BLE001
        pass
    try:
        status, final, html = fetcher(url)
    except Exception as ex:  # noqa: BLE001
        return "unknown", type(ex).__name__
    return classify(url, status, final, html, kind)


def check_many(items: list[tuple[str, str]], fetcher=fetch, robots=robots_allows) -> dict[str, tuple[str, str]]:
    """items = [(url, kind)]. Én vært ad gangen pr. tråd, med pause mellem kald til samme vært."""
    by_host: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for url, kind in dict.fromkeys(items):
        by_host[urlparse(url).netloc.lower()].append((url, kind))
    out: dict[str, tuple[str, str]] = {}

    def run(group):
        for i, (url, kind) in enumerate(group):
            if i:
                time.sleep(PAUSE)
            out[url] = check(url, kind, fetcher, robots)

    with ThreadPoolExecutor(WORKERS) as ex:
        list(ex.map(run, by_host.values()))
    return out

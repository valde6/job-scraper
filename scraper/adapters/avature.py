"""Avature karriereportaler (fx careers.bain.com/jobs, IBM, mange konsulenthuse).

Config:
  url: https://careers.bain.com/jobs        portalens rod (det led, der står før /SearchJobs)
  dk_only: true                             (standard)

Joblisten er server-renderet HTML på <portal>/SearchJobs/?folderOffset=N (10 pr. side). Vi læser kun to ting, der er
stabile på tværs af Avature-temaer: links til opslag (/JobDetail/<slug>/<id> eller /FolderDetail/<slug>/<id>) og
stedet, der står i samme kort som linket. Opslag uden for Danmark springes over uden at hente detaljesiden.
Detaljesiden læses med `extract_posting` (JSON-LD → etiket/værdi-felter → sidens tekst), så et nyt tema ikke
ødelægger noget. robots.txt hos Avature tillader /jobs, men forbyder adresser med `qtvc=` – dem bruger vi ikke.
"""
import re
from urllib.parse import urljoin

from ..common import Job, clean, extract_posting, get, html_to_md, is_denmark, reject, soup, student_fit, topic_tags

PAGE = 10
MAX_PAGES = 80                                   # 800 opslag
LINK_RE = re.compile(r"/(?:JobDetail|FolderDetail)/[^/?#\"']+/(\d+)")
_SKIP_TEXT = re.compile(r"^(learn more|læs mere|read more|apply|ansøg|se job|view job|share)", re.I)


def _card(a):
    """Det mindste element omkring linket, der også indeholder andet end titlen (kortet)."""
    node = a
    for _ in range(6):
        if node.parent is None:
            break
        node = node.parent
        if node.name in ("article", "li") or len(clean(node.get_text(" "))) > len(clean(a.get_text(" "))) + 3:
            return node
    return node


def _location(card, title: str) -> str:
    el = card.find(class_=re.compile(r"subtitle|location|place|city", re.I))
    if el:
        return clean(el.get_text(" "))
    rest = clean(card.get_text(" ")).replace(title, "")
    return clean(_SKIP_TEXT.sub("", rest))[:120]


def listing(base: str) -> list[dict]:
    """[{id, title, url, location}] fra alle sider af joblisten."""
    out, seen = [], set()
    for page in range(MAX_PAGES):
        off = page * PAGE
        html = get(f"{base}/SearchJobs/", params={"folderRecordsPerPage": PAGE, "folderOffset": off,
                                                  "jobRecordsPerPage": PAGE, "jobOffset": off}).text
        s = soup(html)
        new = 0
        for a in s.find_all("a", href=LINK_RE):
            title = clean(a.get_text(" "))
            m = LINK_RE.search(a["href"])
            if not title or _SKIP_TEXT.match(title) or not m or m.group(1) in seen:
                continue
            seen.add(m.group(1))
            new += 1
            card = _card(a)
            out.append({"id": m.group(1), "title": title, "url": urljoin(base + "/", a["href"]),
                        "location": _location(card, title)})
        if new == 0:
            break
    return out


def scrape(cfg):
    base = cfg["url"].rstrip("/")
    items = listing(base)
    jobs = []
    for it in items:
        loc = it["location"]
        if cfg.get("dk_only", True) and loc and not is_denmark(loc):
            continue                                  # udenlandske opslag: ingen grund til at hente detaljesiden
        try:
            p = extract_posting(get(it["url"]).text)
        except Exception:  # noqa: BLE001 – ét opslag, der fejler, må ikke vælte kilden
            continue
        loc = p["location"] or loc
        if cfg.get("dk_only", True) and not is_denmark(loc):
            continue
        title = p["title"] or it["title"]
        desc = html_to_md(p["description_html"])
        fit = student_fit(title, desc + " " + p.get("employment_type", ""))
        if not fit or (fit != "sikker" and not topic_tags(title, desc[:3000])):
            reject(cfg["name"], title, "ikke studiejob", it["url"])
            continue
        jobs.append(Job(company=cfg["name"], title=title, url=it["url"], location=loc, posted=p["posted"],
                        deadline=p["deadline"], description_md=desc, source="avature", external_id=it["id"], fit=fit))
    return len(items), jobs

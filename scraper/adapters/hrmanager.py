"""HR-Manager (Talentech), meget brugt af danske virksomheder og myndigheder.

Config:
  customer: nykredit          (fra candidate.hr-manager.net/...?customer=XXX)
  exclude_title: "regex"      (valgfri) titler der aldrig er relevante, fx sundhedsstuderende på hospitaler
  dk_only: true               (standard)

API'et giver kun 25 opslag, medmindre man beder om flere (`take`). Vi henter alle sider.

Fælles portaler ("Statens Rekrutteringsløsning", "Statens eRekruttering") dækker mange arbejdsgivere. Her står den
rigtige arbejdsgiver i afdelingstræet (`DepartmentTree`), fx
"Statens Rekrutteringsløsning > § 28 TRM (L-HR) - Transportministeriet > Banedanmark > Kommunikation".
Så bruges "Banedanmark" som firmanavn i stedet for portalens navn. Det sker automatisk for portaler,
hvis kundenavn indeholder "rekruttering", eller når `multi_employer: true` er sat.
"""
import re
from datetime import datetime, timezone

from ..common import Job, get, clean, html_to_md, is_denmark, student_fit, topic_tags, reject

API = "https://api.hr-manager.net/jobportal.svc/{c}/positionlist/json/"
PAGE = 200
MAX_PAGES = 15

# Grupperings-noder i afdelingstræet, som ikke er en arbejdsgiver.
_GROUP_RE = re.compile(
    r"^(statens\s+e?rekruttering\w*|statens\s+rekrutteringsløsning|statslige institutioner|selvejende institutioner|"
    r"regioner|kommuner|andre|elever og praktikanter|praktikanter|elever)$", re.I)
_PARAGRAPH_RE = re.compile(r"^§\s*\d+")                     # "§ 28 TRM (L-HR) - Transportministeriet"
_MINISTRY_RE = re.compile(r"ministeri(?:et|um)\b", re.I)


def _date(v):
    m = re.search(r"/Date\((\d+)", str(v or ""))
    if not m:
        return ""
    return datetime.fromtimestamp(int(m.group(1)) / 1000, tz=timezone.utc).date().isoformat()


def _title(p):
    for k in ("Name", "Title", "PositionTitle", "JobTitle", "Headline", "PositionName"):
        if isinstance(p.get(k), str) and p[k].strip():
            return p[k]
    adv = (p.get("Advertisements") or [{}])[0]
    return adv.get("Title") or adv.get("Name") or ""


def _tree(p) -> list[str]:
    """Afdelingstræet som liste af navne fra roden og ned (første gren)."""
    out, node = [], p.get("DepartmentTree")
    for _ in range(10):
        if not isinstance(node, dict):
            break
        name = clean(node.get("Name"))
        if name:
            out.append(name)
        subs = node.get("SubItems") or []
        node = subs[0] if subs else None
    return out


def _ministry_name(node: str) -> str:
    """'§7 FM (F-HR) - Finansministeriet' → 'Finansministeriet'."""
    if " - " in node:
        return clean(node.split(" - ", 1)[1])
    # "§13 MSSB (K-HR) Ministeriet for Samfund og Beredskab" → alt til og med sidste ')' fjernes
    return clean(re.sub(r"^§[^)]*\)+\s*", "", node)) if ")" in node else clean(_PARAGRAPH_RE.sub("", node))


def employer_from_tree(path: list[str], fallback: str) -> str:
    """Den egentlige arbejdsgiver i en fælles portal.

    Spring grupperings-noder over. Er næste node et ministerium (eller en '§'-paragraf), og findes der en institution
    under det, så er institutionen arbejdsgiveren ("Banedanmark", "Institut for Menneskerettigheder"). Er der kun
    ministeriet (eller dets departement), så er det ministeriet.
    """
    nodes = [n for n in path if not _GROUP_RE.match(n)]
    if not nodes:
        return fallback
    first = nodes[0]
    is_ministry = bool(_PARAGRAPH_RE.match(first) or _MINISTRY_RE.search(first))
    if is_ministry:
        ministry = _ministry_name(first) if _PARAGRAPH_RE.match(first) else first
        rest = [n for n in nodes[1:] if not _GROUP_RE.match(n)]
        if rest and not re.search(r"departement", rest[0], re.I):
            return rest[0]
        return ministry
    return first


def _items(customer: str) -> tuple[list[dict], str]:
    items, name = [], ""
    for page in range(MAX_PAGES):
        data = get(API.format(c=customer), params={"incads": 1, "take": PAGE, "skip": page * PAGE}).json()
        if isinstance(data, list):                 # ældre svarform: hele listen på én gang
            return data, name
        name = name or clean(data.get("CustomerName"))
        batch = data.get("Items") or data.get("items") or []
        items.extend(batch)
        total = data.get("PositionCountCustomer") or data.get("PositionCountSearch") or 0
        if len(batch) < PAGE or (total and len(items) >= total):
            break
    return items, name


def _location(p) -> str:
    parts = []
    loc = p.get("PositionLocation")
    if isinstance(loc, dict) and loc.get("Name"):
        parts.append(loc["Name"])
    for k in ("WorkPlace", "WorkPlaceCity", "Location", "Country"):
        if isinstance(p.get(k), (str, int)) and str(p.get(k)).strip():
            parts.append(str(p[k]))
    dep = p.get("Department")
    if not parts and isinstance(dep, dict):
        parts.append(" ".join(str(dep.get(k) or "") for k in ("Address", "Zip", "City")))
    return clean(" ".join(parts))


def scrape(cfg):
    c = cfg["customer"]
    items, customer_name = _items(c)
    multi = cfg.get("multi_employer", "rekruttering" in customer_name.lower())
    exclude = re.compile(cfg["exclude_title"], re.I) if cfg.get("exclude_title") else None
    listed, jobs = 0, []
    for p in items:
        listed += 1
        title = clean(_title(p))
        if exclude and exclude.search(title):
            continue
        adv0 = (p.get("Advertisements") or [{}])[0]
        content = html_to_md(adv0.get("Content", ""))
        fit = student_fit(title, content)
        if not fit or (fit != "sikker" and not topic_tags(title, content[:3000])):
            reject(cfg["name"], title, "ikke studiejob")
            continue
        loc = _location(p)
        if loc and not is_denmark(loc, "denmark" if cfg.get("dk_only", True) else ""):
            continue
        desc_html = adv0.get("Content") or p.get("Description", "")
        url = p.get("AdvertisementUrlSecure") or p.get("AdvertisementUrl") or \
            f"https://candidate.hr-manager.net/ApplicationInit.aspx?cid={p.get('CustomerId','')}&ProjectId={p.get('Id')}"
        company = employer_from_tree(_tree(p), cfg["name"]) if multi else cfg["name"]
        description = html_to_md(desc_html)
        jobs.append(Job(
            company=company, title=title, url=url, apply_url=p.get("ApplicationFormUrl") or url,
            location=loc or "Danmark", posted=_date(p.get("Created")),
            deadline=_date(p.get("ApplicationDue")),
            description_md=description, source="hrmanager", external_id=str(p.get("Id")), fit=fit,
        ))
    return listed, jobs

"""Opdagelse af nye arbejdsgivere via Jobindex (KUN firma-niveau).

Jobindex bruges som pejlemærke: for studiejob i Jobindex' RSS-feeds læses linket i opslaget, så vi kan se,
hvilket rekrutteringssystem arbejdsgiveren bruger (HR-Manager, Emply, Teamtailor, Workday, Oracle, …).
Arbejdsgiveren tilføjes så som direkte kilde i platform/discovered.yaml, og alle job hentes derefter fra
arbejdsgiverens eget system. Intet indhold fra Jobindex gemmes eller vises – kun virksomhedsnavn og kilde-URL.

    python -m scraper.discover_jobindex              # kører i jobradar-workflowet før scrapingen
"""
from __future__ import annotations

import json
import re
import time
import urllib.robotparser as rp
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

import yaml
from bs4 import BeautifulSoup

from .common import clean, get, soup

ROOT = Path(__file__).resolve().parent.parent
PLAT = ROOT / "platform"
SEEN_F = ROOT / "data" / "jobradar" / "discovery_seen.json"
OUT_F = PLAT / "discovered.yaml"
LOG_F = ROOT / "data" / "jobradar" / "discovery_log.json"
MAX_NEW_ADS = 250          # opslag vi læser pr. kørsel (resten tages næste nat)

QUERIES = ["studentermedhjælper", "studentermedarbejder", "studiejob", "student", '"student assistant"',
           "praktikant", "praktik", "graduate", "trainee", '"student worker"', "studerende", "internship"]

NOISE = re.compile(r"jobindex\.|jix|facebook|linkedin|twitter|instagram|youtube|google|apple\.com|cookie|onetrust|"
                   r"cloudflare|gstatic|doubleclick|trustpilot|stepstone|it-jobbank|computerworld|jobunivers|mailto:", re.I)


# ---------------------------------------------------------------- genkendelse af rekrutteringssystemer
def recognize(url: str) -> tuple[str, dict, str] | None:
    """URL fra et opslag → (type, source-config, unik nøgle) eller None. Kræver ingen netværk (undtagen HR-Manager-alias)."""
    u = url.strip()
    p = urlparse(u)
    host, path = p.netloc.lower(), p.path
    if m := re.match(r"([a-z0-9-]+)\.career\.emply\.com$", host):
        return "emply", {"url": f"https://{host}"}, f"emply:{m.group(1)}"
    if "hr-manager.net" in host and (m := re.search(r"[?&]cid=(\d+)", u)):
        return "hrmanager", {"cid": m.group(1), "probe_url": u}, f"hrmanager-cid:{m.group(1)}"
    if m := re.match(r"([a-z0-9-]+)\.teamtailor\.com$", host):
        return "teamtailor", {"url": f"https://{host}"}, f"teamtailor:{host}"
    if re.search(r"/jobs/\d{5,}-[a-z0-9-]+", path) and "promotion=" in p.query:
        return "teamtailor", {"url": f"https://{host}"}, f"teamtailor:{host}"
    if m := re.match(r"([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com$", host):
        segs = [s for s in path.split("/") if s and not re.fullmatch(r"[a-z]{2}-[A-Z]{2}", s)]
        if segs:
            return "workday", {"url": f"https://{host}/{segs[0]}"}, f"workday:{host}/{segs[0]}".lower()
    if host.endswith(".oraclecloud.com") and (m := re.search(r"/sites/([^/?#]+)", path)):
        return "oracle", {"host": f"https://{host}", "site": m.group(1)}, f"oracle:{host}".lower()
    if host in ("jobs.smartrecruiters.com", "careers.smartrecruiters.com"):
        segs = [s for s in path.split("/") if s]
        if segs:
            return "smartrecruiters", {"company_id": segs[0]}, f"smartrecruiters:{segs[0].lower()}"
    if m := re.match(r"([a-z0-9-]+\.yello\.co)$", host):
        if mm := re.search(r"job_board_id=([\w-]+)", p.query) or re.search(r"/job_boards/([\w-]+)", path):
            return "yello", {"url": f"https://{host}/job_boards/{mm.group(1)}"}, f"yello:{mm.group(1)}"
    if host in ("jobs.lever.co", "jobs.eu.lever.co"):
        segs = [s for s in path.split("/") if s]
        if segs:
            return "lever", {"account": segs[0], **({"eu": True} if ".eu." in host else {})}, f"lever:{segs[0].lower()}"
    if "greenhouse.io" in host:
        segs = [s for s in path.split("/") if s]
        if segs:
            return "greenhouse", {"board": segs[0]}, f"greenhouse:{segs[0].lower()}"
    return None


def hrmanager_alias(probe_url: str) -> str | None:
    """Kundealias (fx 'kpmg') står i HTML'en på HR-Managers ansøgningsside som customer=…"""
    try:
        html = get(probe_url, retries=1, timeout=20).text
    except Exception:  # noqa: BLE001
        return None
    m = re.search(r"customer=([A-Za-z0-9_.\-]+)", html)
    return m.group(1).rstrip(".") if m else None


# ---------------------------------------------------------------- Jobindex (kun de tilladte stier)
_robots = None


def allowed(url: str) -> bool:
    global _robots
    if _robots is None:
        _robots = rp.RobotFileParser()
        try:
            _robots.parse(get("https://www.jobindex.dk/robots.txt", retries=1).text.splitlines())
        except Exception:  # noqa: BLE001
            _robots = False
    return bool(_robots) and _robots.can_fetch("*", url)


def rss_items(query: str):
    url = f"https://www.jobindex.dk/jobsoegning.rss?q={quote(query, safe='')}"
    if not allowed(url):
        return []
    xml = get(url, retries=1).text
    out = []
    for it in BeautifulSoup(xml, "xml").find_all("item"):
        link = clean(it.find("link").get_text() if it.find("link") else "")
        title = clean(it.find("title").get_text() if it.find("title") else "")
        if link:
            out.append((link, title))
    return out


def external_links(ad_id: str) -> list[str]:
    links = []
    for url in (f"https://www.jobindex.dk/jobannonce/{ad_id}/", f"https://www.jobindex.dk/vis-job/{ad_id}"):
        if not allowed(url):
            continue
        try:
            r = get(url, retries=1, timeout=20, allow_redirects=True)
        except Exception:  # noqa: BLE001
            continue
        if "jobindex.dk" not in urlparse(r.url).netloc:
            links.append(r.url)              # opslaget viderestiller direkte til arbejdsgiveren
        s = soup(r.text)
        for tag in s.find_all(["a", "iframe"]):
            href = tag.get("href") or tag.get("src") or ""
            if href.startswith("http") and not NOISE.search(href):
                links.append(href[:400])
        time.sleep(0.5)
    return list(dict.fromkeys(links))


# ---------------------------------------------------------------- hovedprogram
def known_keys(employers: list[dict]) -> set[str]:
    keys = set()
    for e in employers:
        s = e.get("source") or {}
        t = s.get("type")
        if t == "emply":
            keys.add(f"emply:{urlparse(s['url']).netloc.split('.')[0]}")
        elif t == "hrmanager" and s.get("customer"):
            keys.add(f"hrmanager:{s['customer'].lower()}")
        elif t == "teamtailor":
            keys.add(f"teamtailor:{urlparse(s['url']).netloc.lower()}")
        elif t == "workday":
            p = urlparse(s["url"])
            keys.add(f"workday:{p.netloc}/{p.path.strip('/').split('/')[0]}".lower())
        elif t == "oracle":
            keys.add(f"oracle:{urlparse(s['host']).netloc}".lower())
        elif t == "smartrecruiters":
            keys.add(f"smartrecruiters:{s['company_id'].lower()}")
        elif t == "yello":
            keys.add(f"yello:{s['url'].rstrip('/').rsplit('/', 1)[-1]}")
        elif t == "lever":
            keys.add(f"lever:{s['account'].lower()}")
        elif t == "greenhouse":
            keys.add(f"greenhouse:{s['board'].lower()}")
        if e.get("cid"):
            keys.add(f"hrmanager-cid:{e['cid']}")
    return keys


def company_from_title(full_title: str) -> str:
    title, _, comp = full_title.rpartition(", ")
    return clean(comp) if title else ""


def main():
    from .adapters import ADAPTERS
    from .common import set_job_types
    from .platform_run import JOB_TYPES, PLATFORM_TERMS, TERM_TYPES
    set_job_types(JOB_TYPES)
    employers = yaml.safe_load((PLAT / "employers.yaml").read_text())["employers"]
    discovered = yaml.safe_load(OUT_F.read_text())["employers"] if OUT_F.exists() else []
    keys = known_keys(employers + discovered)
    names = {e["name"].lower() for e in employers + discovered}
    seen = set(json.loads(SEEN_F.read_text())) if SEEN_F.exists() else set()
    log = {"started": datetime.now(timezone.utc).isoformat(timespec="seconds"), "ads_read": 0, "candidates": [], "added": [], "rejected": []}

    items = {}
    for q in QUERIES:
        try:
            for link, title in rss_items(q):
                items.setdefault(link, title)
        except Exception as e:  # noqa: BLE001
            print("rss fejl", q, e)
        time.sleep(1)
    print("RSS-opslag:", len(items))

    candidates: dict[str, dict] = {}
    for link, full_title in items.items():
        m = re.search(r"(h\d{5,})", link)
        if not m or m.group(1) in seen:
            continue
        if log["ads_read"] >= MAX_NEW_ADS:
            break
        seen.add(m.group(1))
        log["ads_read"] += 1
        for href in external_links(m.group(1)):
            rec = recognize(href)
            if not rec:
                continue
            typ, cfg, key = rec
            if key in keys or key in candidates:
                break
            company = company_from_title(full_title)
            if not company:
                break
            candidates[key] = {"name": company, "type": typ, "cfg": cfg, "evidence": href[:300]}
            break

    for key, c in candidates.items():
        typ, cfg = c["type"], dict(c["cfg"])
        if typ == "hrmanager":
            alias = hrmanager_alias(cfg.pop("probe_url"))
            cid = cfg.pop("cid")
            if not alias:
                log["rejected"].append({**c, "reason": "HR-Manager-alias ikke fundet"})
                continue
            cfg = {"customer": alias}
            if f"hrmanager:{alias.lower()}" in keys:
                continue
            c["cid"] = cid
        name = c["name"]
        if typ not in ADAPTERS:                    # gem den alligevel: kører automatisk, når adapteren findes
            if name.lower() in names:
                name = f"{name} ({typ})"
            discovered.append({"name": name, "career_url": cfg.get("url") or c["evidence"], "status": "mangler-adapter",
                               "source": {"type": typ, **cfg},
                               "discovered": {"at": log["started"][:10], "via": "jobindex-link", "evidence": c["evidence"]}})
            names.add(name.lower()); keys.add(key)
            log["added"].append({"name": name, "type": typ, "listed": None, "note": "mangler adapter"})
            continue
        if name.lower() in names:
            name = f"{name} ({typ})"
        run_cfg = {"type": typ, **cfg, "name": name}
        if typ in TERM_TYPES:
            run_cfg["search_terms"] = PLATFORM_TERMS
        try:
            listed, jobs = ADAPTERS[typ](run_cfg)
        except Exception as e:  # noqa: BLE001
            log["rejected"].append({**c, "reason": f"{type(e).__name__}: {str(e)[:120]}"})
            continue
        log["candidates"].append({**c, "listed": listed, "matched": len(jobs)})
        if listed == 0:
            log["rejected"].append({**c, "reason": "0 opslag"})
            continue
        entry = {"name": name, "career_url": cfg.get("url") or cfg.get("host") or c["evidence"],
                 "status": "opdaget", "source": {"type": typ, **cfg},
                 "discovered": {"at": log["started"][:10], "via": "jobindex-link", "evidence": c["evidence"]}}
        if c.get("cid"):
            entry["cid"] = c["cid"]
        discovered.append(entry)
        names.add(name.lower())
        keys.add(key)
        log["added"].append({"name": name, "type": typ, "listed": listed, "matched": len(jobs)})
        print(f"TILFØJET {name:<40} {typ:<15} listed={listed} matched={len(jobs)}")

    header = ("# Maskinvedligeholdt: arbejdsgivere fundet automatisk via links i studiejob-opslag (scraper/discover_jobindex.py).\n"
              "# Ret gerne navne. Flyt en arbejdsgiver til employers.yaml, hvis den skal have særlige indstillinger.\n")
    OUT_F.write_text(header + yaml.safe_dump({"employers": discovered}, allow_unicode=True, sort_keys=False, width=200))
    SEEN_F.parent.mkdir(parents=True, exist_ok=True)
    SEEN_F.write_text(json.dumps(sorted(seen)[-20000:]))
    LOG_F.write_text(json.dumps(log, ensure_ascii=False, indent=1))
    print(f"Læst {log['ads_read']} nye opslag, {len(candidates)} kandidater, {len(log['added'])} tilføjet, {len(log['rejected'])} afvist")


if __name__ == "__main__":
    main()

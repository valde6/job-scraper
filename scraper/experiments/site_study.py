"""Undersøgelse 2: Hvordan er arbejdsgivernes egne job-sider bygget, og findes 'kun Jobindex'-job også dér?

Læser data/study/targets.json (fra apply_study) og for hver kilde-URL måles:
  - om siden svarer uden browser (status, tekstmængde) eller kræver JavaScript
  - om opslaget har schema.org JobPosting (Google for Jobs) og hvilke felter
  - om robots.txt tillader adgang, og om der er sitemap
  - ATS-signaturer i HTML
For job uden link til et opslag uden for Jobindex: find karrieresiden fra hjemmesiden (browser) og
søg efter jobtitlen dér.
    python -m scraper.experiments.site_study -> data/study/site_study.json + site_summary.json
"""
import json
import re
import time
import urllib.robotparser as rp
from collections import Counter
from pathlib import Path
from urllib.parse import urljoin, urlparse

from ..common import clean, http, jsonld_jobposting, soup
from ..discover import SIG_RE

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "study"
UA = "Mozilla/5.0 (compatible; studiejob-radar/1.0)"
FIELDS = ["title", "description", "datePosted", "validThrough", "hiringOrganization", "jobLocation",
          "employmentType", "identifier", "baseSalary"]
FOLLOW = re.compile(r"karriere|career|job|stilling|ledige|vacanc|arbejd", re.I)
_robots = {}


def robots(url):
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots:
        info = {"parser": None, "sitemaps": [], "ai_block": False}
        try:
            resp = http("GET", base + "/robots.txt", retries=0, timeout=10)
            txt = resp.text if "html" not in resp.headers.get("content-type", "") else ""
            r = rp.RobotFileParser()
            r.parse(txt.splitlines())
            info["parser"] = r
            info["sitemaps"] = [l.split(":", 1)[1].strip() for l in txt.splitlines() if l.lower().startswith("sitemap:")]
            info["ai_block"] = bool(re.search(r"(GPTBot|ClaudeBot|CCBot|anthropic)", txt, re.I))
        except Exception:
            pass
        _robots[base] = info
    info = _robots[base]
    allowed = info["parser"].can_fetch("*", url) if info["parser"] else "ingen robots.txt"
    return {"allowed": allowed, "sitemaps": info["sitemaps"][:3], "ai_block": info["ai_block"]}


def inspect(url):
    info = {"url": url, "host": urlparse(url).netloc}
    try:
        r = http("GET", url, retries=1, timeout=20)
        html = r.text
        s = soup(html)
        for bad in s.select("script, style, noscript"):
            bad.decompose()
        txt = clean(s.get_text(" "))
        jp = jsonld_jobposting(html) or {}
        info.update(status=r.status_code, final=r.url[:200], text_len=len(txt),
                    needs_js=len(txt) < 600, jsonld=bool(jp), jsonld_fields=[f for f in FIELDS if jp.get(f)],
                    sigs=[k for k, rx in SIG_RE.items() if rx.search(html)][:5])
    except Exception as e:  # noqa: BLE001
        info.update(status="fejl", error=str(e)[:150])
    info["robots"] = robots(url)
    return info


def title_key(title):
    t = re.split(r",\s*[^,]+$", title)[0]          # fjern ", Virksomhed"
    words = [w for w in re.findall(r"[\wæøå]{4,}", t.lower()) if w not in ("studentermedhjælper", "student", "assistant")]
    return words[:4]


def find_on_site(home, title):
    """Finder karrieresiden fra forsiden og kigger efter jobtitlen (med browser, da mange lister er JS)."""
    from .. import browser as B
    res = {"home": home, "career_pages": [], "found": False}
    try:
        page = B.render(home, wait_ms=1200, scroll=1, more_clicks=0)
    except Exception as e:  # noqa: BLE001
        res["error"] = str(e)[:120]
        return res
    cands = []
    for txt, href in page["links"]:
        if urlparse(href).netloc and FOLLOW.search((txt or "") + " " + href) and href not in cands:
            cands.append(href)
    key = title_key(title)
    for c in cands[:4]:
        try:
            p = B.render(c, wait_ms=1500, scroll=2, more_clicks=1)
        except Exception:
            continue
        body = (p["text"] + " " + " ".join(t for t, _ in p["links"])).lower()
        hit = sum(1 for w in key if w in body)
        res["career_pages"].append({"url": c[:160], "hits": f"{hit}/{len(key)}"})
        # Følg også et niveau videre til en ledige-stillinger-liste
        if hit < max(2, len(key) - 1):
            for t2, h2 in p["links"][:400]:
                if re.search(r"ledige|stillinger|vacanc|open positions|jobs?$|se alle", t2 or "", re.I) and h2 != c:
                    try:
                        p2 = B.render(h2, wait_ms=1500, scroll=2, more_clicks=1)
                        body2 = (p2["text"] + " " + " ".join(t for t, _ in p2["links"])).lower()
                        hit = max(hit, sum(1 for w in key if w in body2))
                        res["career_pages"].append({"url": h2[:160], "hits": f"{hit}/{len(key)}"})
                    except Exception:
                        pass
                    break
        if hit >= max(2, len(key) - 1):
            res["found"] = True
            break
    return res


def main():
    targets = json.loads((OUT / "targets.json").read_text())
    rows = []
    for n, t in enumerate(targets):
        time.sleep(0.6)
        row = dict(t)
        if t.get("evidence"):
            row["page"] = inspect(t["evidence"])
        elif t["homes"]:
            try:
                row["onsite"] = find_on_site(t["homes"][0], t["title"])
            except Exception as e:  # noqa: BLE001
                row["onsite"] = {"error": str(e)[:150]}
        rows.append(row)
        if n % 20 == 0:
            print(n, t["kind"], (t.get("evidence") or str(t["homes"][:1]))[:80])

    pages = [r["page"] for r in rows if r.get("page")]
    ok = [p for p in pages if p.get("status") == 200]
    hosts = {}
    for p in ok:
        hosts.setdefault(p["host"], p)
    summary = {
        "sider_testet": len(pages), "svarer_200": len(ok),
        "jsonld_jobposting": sum(p["jsonld"] for p in ok),
        "kræver_js": sum(p["needs_js"] for p in ok),
        "jsonld_felter": Counter(f for p in ok for f in p.get("jsonld_fields", [])),
        "jsonld_by_system": Counter(f"{r.get('system') or r['kind']}|{'ja' if r['page'].get('jsonld') else 'nej'}"
                                    for r in rows if r.get("page") and r["page"].get("status") == 200),
        "robots_tilladt": Counter(str(p["robots"].get("allowed")) for p in hosts.values()),
        "robots_sitemap": sum(bool(p["robots"].get("sitemaps")) for p in hosts.values()),
        "robots_blokerer_ai_bots": sum(bool(p["robots"].get("ai_block")) for p in hosts.values()),
        "unikke_værter": len(hosts),
        "fejl": Counter(str(p.get("status")) for p in pages if p.get("status") != 200),
        "kun_jobindex_tjek": Counter("fundet" if r["onsite"].get("found") else ("fejl" if r["onsite"].get("error") else "ikke fundet")
                                     for r in rows if r.get("onsite")),
    }
    (OUT / "site_study.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    (OUT / "site_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=dict))
    print(json.dumps(summary, ensure_ascii=False, indent=1, default=dict))
    for r in rows:
        if r.get("onsite"):
            print("ONSITE", r["paid"], r["title"][:60], r["onsite"].get("found"), r["onsite"].get("career_pages", [])[:3])


if __name__ == "__main__":
    main()

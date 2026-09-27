"""Finder hvilket rekrutteringssystem hver virksomhed bruger.

Crawler karrieresiden (2 niveauer) og leder efter kendte systemers URL'er i HTML og scripts.
Resultat: data/discovery.json.   python -m scraper.discover [--only NAME]
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import urljoin, urlparse

import yaml

from .common import get, soup, clean, jsonld_jobposting

ROOT = Path(__file__).resolve().parent.parent

SIGS = {
    "workday": r"https?://[a-z0-9-]+\.wd\d+\.myworkdayjobs\.com/[^\s\"'<>\\]*",
    "successfactors": r"https?://[a-z0-9.-]*(?:successfactors\.(?:eu|com)|jobs2web\.com|sapsf\.(?:eu|com))[^\s\"'<>\\]*",
    "smartrecruiters": r"https?://(?:jobs|careers|api)\.smartrecruiters\.com/[^\s\"'<>\\]*",
    "greenhouse": r"https?://(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/[^\s\"'<>\\]*|boards-api\.greenhouse\.io[^\s\"'<>\\]*",
    "lever": r"https?://jobs(?:\.eu)?\.lever\.co/[^\s\"'<>\\]*",
    "teamtailor": r"https?://[a-z0-9-]+\.teamtailor\.com[^\s\"'<>\\]*|teamtailor-cdn",
    "hrmanager": r"https?://[a-z0-9.-]*hr-manager\.net/[^\s\"'<>\\]*",
    "emply": r"https?://[a-z0-9.-]*emply\.(?:net|com|dk)[^\s\"'<>\\]*",
    "oracle": r"https?://[a-z0-9.-]+\.oraclecloud\.com/hcmUI/CandidateExperience[^\s\"'<>\\]*",
    "eightfold": r"https?://[a-z0-9.-]*eightfold\.ai[^\s\"'<>\\]*|/api/apply/v2/jobs",
    "avature": r"https?://[a-z0-9.-]+\.avature\.net[^\s\"'<>\\]*",
    "phenom": r"phenompeople|cdn\.phenompeople\.com|/widgets\?|phApp",
    "icims": r"https?://[a-z0-9.-]+\.icims\.com[^\s\"'<>\\]*",
    "jobylon": r"https?://[a-z0-9.-]*jobylon\.com[^\s\"'<>\\]*",
    "varbi": r"https?://[a-z0-9.-]*varbi\.com[^\s\"'<>\\]*",
    "recruitee": r"https?://[a-z0-9-]+\.recruitee\.com[^\s\"'<>\\]*",
    "workable": r"https?://apply\.workable\.com/[^\s\"'<>\\]*",
    "reachmee": r"https?://[a-z0-9.-]*reachmee\.com[^\s\"'<>\\]*",
    "talentsoft/cornerstone": r"https?://[a-z0-9.-]*(?:talent-soft|csod)\.com[^\s\"'<>\\]*",
    "jobindex-widget": r"jobindex\.dk/(?:widget|virksomhed|cgi/jobsearch)[^\s\"'<>\\]*",
    "brassring": r"brassring\.com[^\s\"'<>\\]*",
    "taleo": r"taleo\.net[^\s\"'<>\\]*",
}
SIG_RE = {k: re.compile(v, re.I) for k, v in SIGS.items()}
FOLLOW = re.compile(r"career|karriere|job|vacanc|stilling|opening|position|student|join|arbejd", re.I)


def scan(html: str):
    hits = defaultdict(set)
    for k, rx in SIG_RE.items():
        for m in rx.finditer(html):
            hits[k].add(m.group(0)[:200])
    return hits


def crawl(company: dict, max_pages=30):
    starts = company.get("start_urls") or []
    q = [(u, 0) for u in starts]
    seen, hits, pages, joblike = set(), defaultdict(set), [], []
    domains = {urlparse(u).netloc.split(":")[0].removeprefix("www.") for u in starts}
    while q and len(seen) < max_pages:
        url, depth = q.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            r = get(url, retries=0, timeout=20)
        except Exception as e:  # noqa: BLE001
            pages.append({"url": url, "error": str(e)[:120]})
            continue
        html = r.text
        for k, v in scan(html).items():
            hits[k] |= v
        # iframes/scripts peger ofte på ATS
        s = soup(html)
        for tag in s.find_all(["iframe", "script"], src=True):
            for k, v in scan(tag["src"]).items():
                hits[k] |= v
        n_links = 0
        for a in s.find_all("a", href=True):
            href = urljoin(r.url, a["href"]).split("#")[0]
            txt = clean(a.get_text())
            for k, v in scan(href).items():
                hits[k] |= v
            host = urlparse(href).netloc.removeprefix("www.")
            if re.search(r"/job/|/jobs/|/stilling|/vacanc|/position|jobid|job-id|/opslag", href, re.I):
                n_links += 1
            if depth < 2 and href.startswith("http") and (any(host.endswith(d) or d.endswith(host) for d in domains)) \
                    and (FOLLOW.search(href) or FOLLOW.search(txt)) and href not in seen:
                q.append((href, depth + 1))
        pages.append({"url": r.url, "status": r.status_code, "bytes": len(html), "job_links": n_links,
                      "jsonld_jobposting": bool(jsonld_jobposting(html))})
        if n_links >= 5:
            joblike.append({"url": r.url, "job_links": n_links})
    return {
        "company": company["name"],
        "ats": {k: sorted(v)[:8] for k, v in hits.items()},
        "listing_pages": sorted(joblike, key=lambda x: -x["job_links"])[:5],
        "pages": pages,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", action="append")
    a = ap.parse_args()
    companies = yaml.safe_load((ROOT / "companies.yaml").read_text())["companies"]
    out = []
    for c in companies:
        if a.only and c["name"] not in a.only:
            continue
        res = crawl(c)
        print(f"{c['name']:<32} {', '.join(res['ats']) or '-':<40} lists={len(res['listing_pages'])}")
        out.append(res)
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "discovery.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

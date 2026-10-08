"""Undersøgelse: Hvor kommer Jobindex' studiejob reelt fra?

For hvert aktuelt studiejob i Jobindex' RSS-feeds følges linket til selve opslaget/ansøgningen,
og vi registrerer, om det ender i et rekrutteringssystem (ATS), på arbejdsgiverens egen side,
eller om jobbet kun findes på Jobindex (ansøgning via Jobindex eller e-mail).

    python -m scraper.experiments.apply_study  ->  data/study/apply_study.json + summary.md
"""
import json
import re
import time
from collections import Counter
from pathlib import Path
from urllib.parse import quote, urlparse

from bs4 import BeautifulSoup

from ..adapters.jobindex import QUERIES
from ..common import clean, http, jsonld_jobposting
from ..discover import SIG_RE

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "study"

ATS_DOMAINS = {
    "emply": r"emply\.(?:net|com|dk)", "hr-manager": r"hr-manager\.net", "teamtailor": r"teamtailor\.com",
    "workday": r"myworkdayjobs\.com", "successfactors": r"successfactors\.(?:eu|com)|jobs2web|sapsf",
    "smartrecruiters": r"smartrecruiters\.com", "varbi": r"varbi\.com", "jobylon": r"jobylon\.com",
    "reachmee": r"reachmee\.com", "recruitee": r"recruitee\.com", "lever": r"lever\.co", "greenhouse": r"greenhouse\.io",
    "oracle": r"oraclecloud\.com", "talentsoft": r"talent-soft\.com|cornerstone", "workable": r"workable\.com",
    "homerun": r"homerun\.co", "jobteaser": r"jobteaser\.com", "thehub": r"thehub\.io", "hrmanager-alt": r"hrmanager",
    "peoplexs": r"peoplexs", "zalaris": r"zalaris", "visma": r"visma", "jobnet": r"jobnet\.dk", "icims": r"icims\.com",
    "avature": r"avature\.net", "phenom": r"phenompeople", "eightfold": r"eightfold\.ai", "bamboohr": r"bamboohr",
    "personio": r"personio\.", "career-site": r"career\.|careers\.|karriere\.|job\.|jobs\.",
}
ATS_RE = {k: re.compile(v, re.I) for k, v in ATS_DOMAINS.items()}


def classify(url: str, html: str):
    host = urlparse(url).netloc.lower()
    if not host:
        return "ukendt", None
    if host.endswith("jobindex.dk"):
        return "kun-jobindex", None
    for k, rx in ATS_RE.items():
        if k != "career-site" and rx.search(host):
            return "ats", k
    sig = [k for k, rx in SIG_RE.items() if rx.search(html or "")]
    sig = [s for s in sig if s not in ("jobindex-widget",)]
    if sig:
        return "ats", sig[0] + " (indlejret)"
    return "egen-side", None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    items, seen = [], set()
    for q in QUERIES:
        time.sleep(1)
        try:
            xml = http("GET", f"https://www.jobindex.dk/jobsoegning.rss?q={quote(q, safe='')}", retries=1).text
        except Exception:
            continue
        for it in BeautifulSoup(xml, "xml").find_all("item"):
            link = clean(it.find("link").get_text() if it.find("link") else "")
            if not link or link in seen:
                continue
            seen.add(link)
            title = clean(it.find("title").get_text() if it.find("title") else "")
            d = it.find("description")
            desc = d.get_text() if d else ""
            items.append({"link": link, "title": title, "paid": "PaidJob" in desc,
                          "robot": "robotjob" in desc.lower() and "PaidJob" not in desc,
                          "teaser_mail": bool(re.search(r"mailto:|@[a-z0-9-]+\.(?:dk|com)", desc, re.I))})
    print("opslag:", len(items))

    for n, r in enumerate(items):
        time.sleep(0.7)
        try:
            resp = http("GET", r["link"], retries=1, timeout=20, allow_redirects=True)
            final, html = resp.url, resp.text
            r["first_hop"] = urlparse(final).netloc
            if urlparse(final).netloc.endswith("jobindex.dk"):
                # betalt opslag hos Jobindex: find "Ansøg"-knappen og følg den
                s = BeautifulSoup(html, "lxml")
                a = s.select_one("a[href*='/c?t=']")
                if a:
                    href = a["href"] if a["href"].startswith("http") else "https://www.jobindex.dk" + a["href"]
                    time.sleep(0.5)
                    try:
                        r2 = http("GET", href, retries=1, timeout=20, allow_redirects=True)
                        final, html = r2.url, r2.text
                    except Exception as e:  # noqa: BLE001
                        r["apply_error"] = str(e)[:120]
                        resp2 = getattr(e, "response", None)
                        if resp2 is not None:
                            final = resp2.url
                else:
                    r["apply_mail"] = bool(s.select_one("a[href^='mailto:']"))
                    r["apply_form"] = bool(s.select_one("form[action*='ansoeg'], a[href*='ansoeg'], a[href*='apply']"))
            r["final"] = final[:300]
            r["kind"], r["system"] = classify(final, html)
            r["jsonld"] = bool(jsonld_jobposting(html)) if r["kind"] != "kun-jobindex" else False
        except Exception as e:  # noqa: BLE001
            r["kind"], r["system"], r["error"] = "fejl", None, str(e)[:160]
        if n % 25 == 0:
            print(n, r.get("kind"), r.get("system"), r.get("final", "")[:80])

    kinds = Counter(r["kind"] for r in items)
    systems = Counter(r["system"] for r in items if r["kind"] == "ats")
    paid = Counter((r["paid"], r["kind"]) for r in items)
    jsonld = Counter(r["kind"] for r in items if r.get("jsonld"))
    hosts = Counter(urlparse(r.get("final", "")).netloc for r in items if r["kind"] == "egen-side")
    summary = {"n": len(items), "kinds": kinds, "systems": systems.most_common(),
               "paid_vs_kind": {f"{'betalt' if k[0] else 'robot/gratis'}|{k[1]}": v for k, v in paid.items()},
               "jsonld_by_kind": jsonld, "egen_side_hosts": hosts.most_common(40)}
    (OUT / "apply_study.json").write_text(json.dumps(items, ensure_ascii=False, indent=1))
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=dict))
    print(json.dumps(summary, ensure_ascii=False, indent=1, default=dict))


if __name__ == "__main__":
    main()

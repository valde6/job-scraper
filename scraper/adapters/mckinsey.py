"""McKinsey & Company. Karrieresiden henter jobbene fra et offentligt JSON-API (samme kald som siden selv laver):

  GET https://gateway.mckinsey.com/apigw-x0cceuow60/v1/api/jobs/search?pageSize=50&start=1&cities=Copenhagen&lang=en
  → {"numFound": 14, "docs": [{"jobID", "title", "friendlyURL", "jobApplyURL", "whatYouWillDo", ...}]}

Mange opslag er globale (91 byer), men søgningen på `cities` giver kun dem, der også gælder byen.
Opslaget vises på https://www.mckinsey.com/careers/search-jobs/jobs/<friendlyURL>.

Config:
  city: Copenhagen      (valgfri; standard)
"""
from urllib.parse import quote

from ..common import Job, clean, get, html_to_md, reject, robots_allows, student_fit, topic_tags

API = "https://gateway.mckinsey.com/apigw-x0cceuow60/v1/api/jobs/search"
JOB_URL = "https://www.mckinsey.com/careers/search-jobs/jobs/{}"
PAGE = 50


def _desc(d: dict) -> str:
    parts = []
    for head, key in (("Who you'll work with", "whoYouWillWorkWith"), ("What you'll do", "whatYouWillDo"),
                      ("Your qualifications and skills", "yourBackground")):
        if d.get(key):
            parts.append(f"## {head}\n\n{html_to_md(d[key])}")
    return "\n\n".join(parts)


def scrape(cfg):
    city = cfg.get("city", "Copenhagen")
    if not robots_allows(JOB_URL.format("x")):
        raise RuntimeError("robots.txt forbyder mckinsey.com/careers")
    listed, jobs, start = 0, [], 1
    headers = {"Accept": "application/json", "Referer": "https://www.mckinsey.com/careers/search-jobs"}
    while True:
        data = get(f"{API}?pageSize={PAGE}&start={start}&cities={quote(city)}&lang=en", headers=headers).json() or {}
        docs = data.get("docs") or []
        for d in docs:
            listed += 1
            title = clean(d.get("title"))
            desc = _desc(d)
            fit = student_fit(title, desc)
            if not fit or (fit != "sikker" and not topic_tags(title, desc[:3000])):
                reject(cfg["name"], title, "ikke studiejob")
                continue
            url = JOB_URL.format(d.get("friendlyURL") or d.get("jobID"))
            jobs.append(Job(company=cfg["name"], title=title, url=url, apply_url=d.get("jobApplyURL") or url,
                            location=city, description_md=desc, source="mckinsey",
                            external_id=str(d.get("jobID") or url), fit=fit))
        start += PAGE
        if not docs or start > (data.get("numFound") or 0) or start > 500:
            break
    return listed, jobs

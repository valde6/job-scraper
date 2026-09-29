"""Workday (myworkdayjobs.com). Bruger det samme JSON-API som Workdays egen side.

Config: url: https://lego.wd103.myworkdayjobs.com/LEGO_External
"""
import re
from urllib.parse import urlparse

from ..common import Job, post, get, html_to_md, is_denmark, is_student, is_student_body, clean, student_fit, topic_tags

SEARCH_TERMS = ["student", "studentermedhjælper", "student assistant", "studiejob", "part-time", "deltid"]


def _parts(url: str):
    u = urlparse(url)
    tenant = u.netloc.split(".")[0]
    segs = [s for s in u.path.split("/") if s and not re.fullmatch(r"[a-z]{2}-[A-Z]{2}", s)]
    site = segs[0]
    base = f"{u.scheme}://{u.netloc}"
    return base, tenant, site


def scrape(cfg):
    base, tenant, site = _parts(cfg["url"])
    api = f"{base}/wday/cxs/{tenant}/{site}"
    seen, listed, jobs = set(), 0, []
    for term in cfg.get("search_terms", SEARCH_TERMS):
        offset = 0
        while offset < 400:
            r = post(f"{api}/jobs", json={"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": term},
                     headers={"Content-Type": "application/json", "Accept": "application/json"})
            data = r.json()
            posts = data.get("jobPostings") or []
            for p in posts:
                path = p.get("externalPath")
                if not path or path in seen:
                    continue
                seen.add(path)
                listed += 1
                title = clean(p.get("title"))
                loc = clean(p.get("locationsText"))
                # "2 Locations" skjuler landet -> tjek detaljer
                if not is_denmark(loc, path) and not re.search(r"\d+\s+locations?", loc, re.I):
                    continue
                if not is_student(title) and not cfg.get("check_body", True):
                    continue
                d = get(f"{api}{path}", headers={"Accept": "application/json"}).json()
                info = d.get("jobPostingInfo") or {}
                country = ((info.get("country") or {}).get("descriptor")) or ""
                locs = [info.get("location") or ""] + (info.get("additionalLocations") or [])
                if not is_denmark(country, " ".join(locs), loc):
                    continue
                desc = html_to_md(info.get("jobDescription"))
                fit = student_fit(title, desc)
                if not fit or (fit != "sikker" and not topic_tags(title, desc[:3000])):
                    continue
                jobs.append(Job(
                    company=cfg["name"], title=title,
                    url=info.get("externalUrl") or f"{base}/{site}{path}",
                    apply_url=(info.get("externalUrl") or f"{base}/{site}{path}") + "/apply",
                    location=", ".join(x for x in locs if x) or loc,
                    posted=info.get("startDate") or "",
                    description_md=html_to_md(info.get("jobDescription")),
                    source="workday", external_id=info.get("jobReqId") or path, fit=fit,
                ))
            offset += 20
            if offset >= (data.get("total") or 0) or not posts:
                break
    return listed, jobs

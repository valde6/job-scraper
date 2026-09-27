"""Eightfold PCS (fx Microsoft: apply.careers.microsoft.com).

Config: url: https://apply.careers.microsoft.com   domain: microsoft.com
"""
from ..common import Job, get, html_to_md, is_denmark, is_student, clean


def scrape(cfg):
    base, dom = cfg["url"].rstrip("/"), cfg["domain"]
    listed, jobs, start = 0, [], 0
    while start < 500:
        data = get(f"{base}/api/apply/v2/jobs", params={"domain": dom, "start": start, "num": 50,
                                                        "location": "Denmark", "sort_by": "timestamp"}).json()
        items = data.get("positions") or []
        for p in items:
            listed += 1
            title = clean(p.get("name"))
            locs = " | ".join(p.get("locations") or [p.get("location") or ""])
            if not (is_student(title) and is_denmark(locs)):
                continue
            d = get(f"{base}/api/apply/v2/jobs/{p['id']}", params={"domain": dom}).json()
            url = p.get("canonicalPositionUrl") or f"{base}/careers/job/{p['id']}"
            jobs.append(Job(company=cfg["name"], title=title, url=url, location=locs,
                            description_md=html_to_md(d.get("job_description")), source="eightfold",
                            external_id=str(p.get("ats_job_id") or p["id"])))
        start += 50
        if start >= (data.get("count") or 0) or not items:
            break
    return listed, jobs

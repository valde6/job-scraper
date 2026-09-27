"""Greenhouse job board API. Config: board: netcompany"""
import html as _html

from ..common import Job, get, html_to_md, is_denmark, is_student, clean


def scrape(cfg):
    data = get(f"https://boards-api.greenhouse.io/v1/boards/{cfg['board']}/jobs", params={"content": "true"}).json()
    listed, jobs = 0, []
    for p in data.get("jobs", []):
        listed += 1
        title = clean(p.get("title"))
        loc = (p.get("location") or {}).get("name", "")
        if not (is_student(title) and is_denmark(loc)):
            continue
        jobs.append(Job(
            company=cfg["name"], title=title, url=p.get("absolute_url", ""), location=loc,
            posted=(p.get("updated_at") or "")[:10],
            description_md=html_to_md(_html.unescape(p.get("content") or "")),
            source="greenhouse", external_id=str(p.get("id")),
        ))
    return listed, jobs

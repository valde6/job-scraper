"""Lever postings API. Config: account: danskecommodities (eu: true hvis api.eu.lever.co)"""
from ..common import Job, get, html_to_md, is_denmark, is_student, clean


def scrape(cfg):
    host = "api.eu.lever.co" if cfg.get("eu") else "api.lever.co"
    data = get(f"https://{host}/v0/postings/{cfg['account']}", params={"mode": "json"}).json()
    listed, jobs = 0, []
    for p in data:
        listed += 1
        title = clean(p.get("text"))
        cats = p.get("categories") or {}
        loc = " | ".join([cats.get("location") or ""] + (cats.get("allLocations") or []))
        if not (is_student(title) and is_denmark(loc, p.get("country"))):
            continue
        desc = html_to_md(p.get("description")) + "\n\n" + "\n\n".join(
            f"## {l.get('text')}\n" + html_to_md(l.get("content")) for l in p.get("lists") or [])
        jobs.append(Job(
            company=cfg["name"], title=title, url=p.get("hostedUrl", ""), apply_url=p.get("applyUrl", ""),
            location=loc, description_md=desc + "\n\n" + html_to_md(p.get("additional")),
            source="lever", external_id=p.get("id", ""),
        ))
    return listed, jobs

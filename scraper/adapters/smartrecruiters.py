"""SmartRecruiters offentligt API. Config: company_id: BangOlufsen"""
from ..common import Job, get, html_to_md, is_student, clean

API = "https://api.smartrecruiters.com/v1/companies/{cid}/postings"


def scrape(cfg):
    cid = cfg["company_id"]
    listed, jobs, offset = 0, [], 0
    while True:
        data = get(API.format(cid=cid), params={"country": "dk", "limit": 100, "offset": offset}).json()
        items = data.get("content") or []
        for p in items:
            listed += 1
            title = clean(p.get("name"))
            if not is_student(title):
                continue
            d = get(f"{API.format(cid=cid)}/{p['id']}").json()
            secs = (d.get("jobAd") or {}).get("sections") or {}
            desc = "\n\n".join(html_to_md(v.get("text")) for v in secs.values() if isinstance(v, dict))
            loc = d.get("location") or {}
            jobs.append(Job(
                company=cfg["name"], title=title,
                url=d.get("postingUrl") or f"https://jobs.smartrecruiters.com/{cid}/{p['id']}",
                apply_url=d.get("applyUrl") or "",
                location=", ".join(x for x in (loc.get("city"), loc.get("country")) if x),
                posted=(d.get("releasedDate") or "")[:10], description_md=desc,
                source="smartrecruiters", external_id=p["id"],
            ))
        offset += 100
        if offset >= (data.get("totalFound") or 0) or not items:
            break
    return listed, jobs

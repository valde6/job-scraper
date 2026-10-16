"""SmartRecruiters offentligt API. Config: company_id: BangOlufsen"""
from ..common import Job, get, html_to_md, clean, reject, student_fit, topic_tags

API = "https://api.smartrecruiters.com/v1/companies/{cid}/postings"
MAX_DETAILS = 150


def scrape(cfg):
    cid = cfg["company_id"]
    listed, jobs, offset, fetched = 0, [], 0, 0
    while True:
        data = get(API.format(cid=cid), params={"country": "dk", "limit": 100, "offset": offset}).json()
        items = data.get("content") or []
        for p in items:
            listed += 1
            title = clean(p.get("name"))
            if fetched >= MAX_DETAILS and not student_fit(title):
                continue                      # mange opslag: herefter kun detaljer for titler, der ligner studiejob
            fetched += 1
            try:
                d = get(f"{API.format(cid=cid)}/{p['id']}").json()
            except Exception:  # noqa: BLE001 – ét ødelagt opslag (400/500) må ikke vælte hele kilden
                d = {}
            secs = (d.get("jobAd") or {}).get("sections") or {}
            desc = "\n\n".join(html_to_md(v.get("text")) for v in secs.values() if isinstance(v, dict))
            # Samme filter som de andre adaptere: titel ELLER opslagstekst (før: kun titlen, så fx
            # "Junior Consultant (part-time, alongside your studies)" røg ud).
            fit = student_fit(title, desc)
            if not fit or (fit != "sikker" and not topic_tags(title, desc[:3000])):
                reject(cfg["name"], title, "ikke studiejob")
                continue
            loc = d.get("location") or {}
            jobs.append(Job(
                company=cfg["name"], title=title,
                url=d.get("postingUrl") or f"https://jobs.smartrecruiters.com/{cid}/{p['id']}",
                apply_url=d.get("applyUrl") or "",
                location=", ".join(x for x in (loc.get("city"), loc.get("country")) if x),
                posted=(d.get("releasedDate") or "")[:10], description_md=desc,
                source="smartrecruiters", external_id=p["id"], fit=fit,
            ))
        offset += 100
        if offset >= (data.get("totalFound") or 0) or not items:
            break
    return listed, jobs

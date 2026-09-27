"""HR-Manager (Talentech), meget brugt af danske virksomheder og myndigheder.

Config: customer: nykredit   (fra candidate.hr-manager.net/...?customer=XXX)
"""
from ..common import Job, get, clean, html_to_md, is_denmark, is_student

API = "https://api.hr-manager.net/jobportal.svc/{c}/positionlist/json/"


def scrape(cfg):
    c = cfg["customer"]
    data = get(API.format(c=c), params={"incads": 1}).json()
    if isinstance(data, list):
        items = data
    else:
        items = data.get("Items") or data.get("items") or []
    listed, jobs = 0, []
    for p in items:
        listed += 1
        title = clean(p.get("Name") or p.get("Title"))
        if not is_student(title):
            continue
        loc = clean(" ".join(str(p.get(k) or "") for k in ("WorkPlace", "WorkPlaceCity", "Location", "Country")))
        if loc and not is_denmark(loc, "denmark" if cfg.get("dk_only", True) else ""):
            continue
        adv = p.get("Advertisements") or []
        desc_html = (adv[0].get("Content") if adv else "") or p.get("Description", "")
        url = p.get("AdvertisementUrlSecure") or p.get("AdvertisementUrl") or \
            f"https://candidate.hr-manager.net/ApplicationInit.aspx?cid={p.get('CustomerId','')}&ProjectId={p.get('Id')}"
        jobs.append(Job(
            company=cfg["name"], title=title, url=url, apply_url=p.get("ApplicationFormUrl") or url,
            location=loc or "Danmark", posted=(p.get("Created") or "")[:10],
            deadline=(p.get("ApplicationDue") or "")[:10],
            description_md=html_to_md(desc_html), source="hrmanager", external_id=str(p.get("Id")),
        ))
    return listed, jobs

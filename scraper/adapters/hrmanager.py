"""HR-Manager (Talentech), meget brugt af danske virksomheder og myndigheder.

Config: customer: nykredit   (fra candidate.hr-manager.net/...?customer=XXX)
"""
import re
from datetime import datetime, timezone

from ..common import Job, get, clean, html_to_md, is_denmark, is_student, is_student_body, student_fit, topic_tags

API = "https://api.hr-manager.net/jobportal.svc/{c}/positionlist/json/"


def _date(v):
    m = re.search(r"/Date\((\d+)", str(v or ""))
    if not m:
        return ""
    return datetime.fromtimestamp(int(m.group(1)) / 1000, tz=timezone.utc).date().isoformat()


def _title(p):
    for k in ("Name", "Title", "PositionTitle", "JobTitle", "Headline", "PositionName"):
        if isinstance(p.get(k), str) and p[k].strip():
            return p[k]
    adv = (p.get("Advertisements") or [{}])[0]
    return adv.get("Title") or adv.get("Name") or ""


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
        title = clean(_title(p))
        adv0 = (p.get("Advertisements") or [{}])[0]
        content = html_to_md(adv0.get("Content", ""))
        fit = student_fit(title, content)
        if not fit or (fit != "sikker" and not topic_tags(title, content[:3000])):
            continue
        loc = clean(" ".join(str(p.get(k) or "") for k in ("WorkPlace", "WorkPlaceCity", "Location", "PositionLocation", "Country")
                             if isinstance(p.get(k), (str, int))))
        if loc and not is_denmark(loc, "denmark" if cfg.get("dk_only", True) else ""):
            continue
        adv = p.get("Advertisements") or []
        desc_html = (adv[0].get("Content") if adv else "") or p.get("Description", "")
        url = p.get("AdvertisementUrlSecure") or p.get("AdvertisementUrl") or \
            f"https://candidate.hr-manager.net/ApplicationInit.aspx?cid={p.get('CustomerId','')}&ProjectId={p.get('Id')}"
        jobs.append(Job(
            company=cfg["name"], title=title, url=url, apply_url=p.get("ApplicationFormUrl") or url,
            location=loc or "Danmark", posted=_date(p.get("Created")),
            deadline=_date(p.get("ApplicationDue")),
            description_md=html_to_md(desc_html), source="hrmanager", external_id=str(p.get("Id")), fit=fit,
        ))
    return listed, jobs

"""Nordea: eget JSON-API bag nordea.com/en/careers/vacant-positions. Opslagene ligger på careers.nordea.com."""
from datetime import date
import html as _html

from ..common import Job, get, soup, clean, html_to_md, is_denmark, student_fit, topic_tags, jsonld_jobposting, find_deadline

API = "https://www.nordea.com/en/api/jobs-list"


def scrape(cfg):
    listed, jobs, seen = 0, [], set()
    for q in cfg.get("search_terms", ["student", "studentermedhjælper", "part-time"]):
        for page in range(0, 6):
            data = get(API, params={"_format": "json", "items_per_page": 50, "page": page, "search": q}).json()
            items = data.get("results") or []
            for p in items:
                url = _html.unescape(_html.unescape(p.get("field_ad_url") or p.get("url") or ""))
                if not url or url in seen:
                    continue
                seen.add(url)
                listed += 1
                title = clean(_html.unescape(p.get("title") or ""))
                loc = clean(p.get("location_name"))
                if not is_denmark(loc):
                    continue
                cat = _html.unescape(p.get("category_name") or "")
                fit = student_fit(title, cat)
                if not fit and "student" in cat.lower() and not any(w in title.lower() for w in ("intern", "praktik", "trainee", "graduate", "harjoittel")):
                    fit = "sandsynlig"
                if not fit:
                    continue
                desc_md = ""
                try:
                    h = get(url).text
                    jp = jsonld_jobposting(h) or {}
                    s = soup(h)
                    el = s.select_one("[itemprop=description], .jobdescription, .job")
                    desc_md = html_to_md(jp.get("description")) if jp.get("description") else html_to_md(str(el) if el else "")
                except Exception:
                    pass
                if fit != "sikker" and not topic_tags(title, desc_md[:3000]):
                    continue
                jobs.append(Job(company=cfg["name"], title=title, url=url, apply_url=url, location=loc,
                                posted=p.get("created", ""), deadline=p.get("field_apply_due") or find_deadline(desc_md, date.today().year) or "",
                                description_md=desc_md, source="nordea", external_id=p.get("nid") or url, fit=fit))
            if len(items) < 50:
                break
    return listed, jobs

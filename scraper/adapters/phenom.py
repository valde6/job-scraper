"""Phenom People karrieresider (fx jobs.arla.com). Joblisten ligger som JSON i phApp.ddo på siden.

Config: url: https://jobs.arla.com/global/en
"""
import json
import re
from urllib.parse import quote

from ..common import Job, get, html_to_md, is_denmark, is_student, clean


def _ddo(html: str) -> dict:
    m = re.search(r"phApp\.ddo\s*=\s*", html)
    if not m:
        return {}
    try:
        obj, _ = json.JSONDecoder().raw_decode(html[m.end():])
        return obj
    except ValueError:
        return {}


def scrape(cfg):
    base = cfg["url"].rstrip("/")
    listed, jobs, seen = 0, [], set()
    for kw in cfg.get("search_terms", ["student", "studentermedhjælper"]):
        for frm in range(0, 200, 10):
            ddo = _ddo(get(f"{base}/search-results?keywords={quote(kw)}&from={frm}&s=1").text)
            res = (ddo.get("eagerLoadRefineSearch") or {})
            items = ((res.get("data") or {}).get("jobs")) or []
            for p in items:
                jid = p.get("jobId") or p.get("jobSeqNo")
                if jid in seen:
                    continue
                seen.add(jid)
                listed += 1
                title = clean(p.get("title"))
                loc = ", ".join(x for x in (p.get("city"), p.get("state"), p.get("country")) if x)
                if not (is_student(title) and is_denmark(loc, " ".join(p.get("multi_location") or []))):
                    continue
                url = f"{base}/job/{jid}"
                desc = p.get("descriptionTeaser") or ""
                try:
                    dd = _ddo(get(url).text)
                    desc = ((dd.get("jobDetail") or {}).get("data") or {}).get("job", {}).get("description") or desc
                except Exception:
                    pass
                jobs.append(Job(company=cfg["name"], title=title, url=url, apply_url=p.get("applyUrl") or url,
                                location=loc, posted=(p.get("postedDate") or "")[:10], description_md=html_to_md(desc),
                                source="phenom", external_id=str(jid)))
            if len(items) < 10 or frm + 10 >= (res.get("totalHits") or 0):
                break
    return listed, jobs

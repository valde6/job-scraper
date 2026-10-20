"""Workable (apply.workable.com/<konto>). Samme JSON-API som Workables egen jobside; robots.txt tillader alt.

  POST https://apply.workable.com/api/v3/accounts/<konto>/jobs   {"query": "", "token": <næste side>}
       → {"results": [{"shortcode", "title", "location": {"city", "country", "countryCode"}, "published", ...}],
          "nextPage": "<token>"}
  GET  https://apply.workable.com/api/v2/accounts/<konto>/jobs/<shortcode>   → beskrivelse og krav

Config: account: novonordiskfoundation
"""
from ..common import Job, clean, get, html_to_md, post, reject, student_fit, topic_tags

BASE = "https://apply.workable.com"


def scrape(cfg):
    acct = cfg["account"]
    listed, jobs, token = 0, [], None
    for _ in range(20):
        body = {"query": "", "location": [], "department": [], "worktype": [], "remote": []}
        if token:
            body["token"] = token
        data = post(f"{BASE}/api/v3/accounts/{acct}/jobs", json=body).json() or {}
        for r in data.get("results") or []:
            listed += 1
            title = clean(r.get("title"))
            loc = r.get("location") or {}
            if (loc.get("countryCode") or "").upper() != "DK":
                continue
            d = get(f"{BASE}/api/v2/accounts/{acct}/jobs/{r['shortcode']}").json() or {}
            desc = "\n\n".join(html_to_md(d.get(k)) for k in ("description", "requirements", "benefits") if d.get(k))
            fit = student_fit(title, desc)
            if not fit or (fit != "sikker" and not topic_tags(title, desc[:3000])):
                reject(cfg["name"], title, "ikke studiejob")
                continue
            url = f"{BASE}/{acct}/j/{r['shortcode']}/"
            jobs.append(Job(company=cfg["name"], title=title, url=url, apply_url=url + "apply/",
                            location=", ".join(x for x in (loc.get("city"), loc.get("country")) if x),
                            posted=(r.get("published") or "")[:10], description_md=desc, source="workable",
                            external_id=r["shortcode"], fit=fit))
        token = data.get("nextPage")
        if not token:
            break
    return listed, jobs

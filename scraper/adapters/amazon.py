"""amazon.jobs JSON-søgning, filtreret til Danmark."""
from ..common import Job, get, html_to_md, is_student, clean


def scrape(cfg):
    listed, jobs, offset = 0, [], 0
    while offset < 500:
        data = get("https://www.amazon.jobs/en/search.json", params={
            "normalized_country_code[]": "DNK", "result_limit": 100, "offset": offset, "sort": "recent"}).json()
        items = data.get("jobs") or []
        for p in items:
            listed += 1
            title = clean(p.get("title"))
            if not is_student(title):
                continue
            desc = "\n\n".join(html_to_md(p.get(k)) for k in ("description", "basic_qualifications", "preferred_qualifications"))
            url = "https://www.amazon.jobs" + (p.get("job_path") or "")
            jobs.append(Job(company=cfg["name"], title=title, url=url, apply_url=p.get("url_next_step") or url,
                            location=p.get("normalized_location") or p.get("location") or "", posted=p.get("posted_date", ""),
                            description_md=desc, source="amazon", external_id=p.get("id_icims") or p.get("id", "")))
        offset += 100
        if offset >= (data.get("hits") or 0) or not items:
            break
    return listed, jobs

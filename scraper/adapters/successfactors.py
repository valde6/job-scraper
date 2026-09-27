"""SAP SuccessFactors Career Site Builder (fx careers.vestas.com, careers.ey.com).

Config:
  url: https://careers.vestas.com          (CSB-domænet)
  location: Denmark                         (valgfri, sendes som locationsearch)
Søgesiden /search/?q=...&locationsearch=... er server-renderet HTML.
"""
from urllib.parse import urljoin, quote

from ..common import Job, get, soup, clean, html_to_md, is_denmark, is_student, jsonld_jobposting, jsonld_location

TERMS = ["student", "studentermedhjælper"]


def scrape(cfg):
    base = cfg["url"].rstrip("/")
    loc = cfg.get("location", "Denmark")
    seen, listed, jobs = set(), 0, []
    for term in cfg.get("search_terms", TERMS):
        start = 0
        while start < 300:
            url = f"{base}/search/?q={quote(term)}&locationsearch={quote(loc)}&startrow={start}"
            s = soup(get(url).text)
            rows = s.select("tr.data-row") or s.select("li.job-tile") or s.select("[class*=jobResultItem]")
            links = []
            for row in rows:
                a = row.select_one("a.jobTitle-link") or row.select_one("a[href*='/job/']")
                if not a:
                    continue
                l = row.select_one(".jobLocation") or row.select_one("[class*=location]")
                links.append((clean(a.get_text()), urljoin(base, a["href"]), clean(l.get_text() if l else "")))
            if not rows:  # fallback: alle /job/-links
                for a in s.select("a[href*='/job/']"):
                    links.append((clean(a.get_text()), urljoin(base, a["href"]), ""))
            new = 0
            for title, href, l in links:
                if href in seen or not title:
                    continue
                seen.add(href)
                new += 1
                listed += 1
                if not is_student(title):
                    continue
                html = get(href).text
                jp = jsonld_jobposting(html) or {}
                ds = soup(html)
                desc = ds.select_one("[itemprop=description]") or ds.select_one(".jobdescription") or ds.select_one(".job")
                location = l or jsonld_location(jp) or clean((ds.select_one("[itemprop=jobLocation]") or ds.new_tag("x")).get_text())
                if not is_denmark(location, loc if cfg.get("location_is_dk_only") else ""):
                    continue
                apply = ds.select_one("a.dialogApplyBtn, a[href*='apply'], a.apply")
                jobs.append(Job(
                    company=cfg["name"], title=title, url=href,
                    apply_url=urljoin(base, apply["href"]) if apply and apply.get("href", "").startswith(("/", "http")) else href,
                    location=location, posted=jp.get("datePosted", ""),
                    deadline=(jp.get("validThrough") or "")[:10],
                    description_md=html_to_md(str(desc) if desc else jp.get("description")),
                    source="successfactors", external_id=href.rstrip("/").split("/")[-1],
                ))
            if new == 0 or len(links) < 10:
                break
            start += len(links)
    return listed, jobs

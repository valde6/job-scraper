"""Teamtailor karrieresider. Config: url: https://nordnet.teamtailor.com (eller eget domæne)

Bruger RSS-feedet /jobs.rss som indeholder titel, link, lokation og beskrivelse.
"""
from bs4 import BeautifulSoup
from ..common import Job, get, soup, clean, html_to_md, is_denmark, is_student, jsonld_jobposting, jsonld_location


def scrape(cfg):
    base = cfg["url"].rstrip("/")
    xml = get(f"{base}/jobs.rss").text
    s = BeautifulSoup(xml, "xml")
    listed, jobs = 0, []
    for it in s.find_all("item"):
        listed += 1
        title = clean(it.find("title").get_text() if it.find("title") else "")
        link = clean(it.find("link").get_text() if it.find("link") else "") or clean(it.find("guid").get_text() if it.find("guid") else "")
        if not is_student(title):
            continue
        loc_tags = it.find_all(["location", "city", "locations"])
        loc = " ".join(clean(t.get_text()) for t in loc_tags)
        desc = it.find("description")
        desc_md = html_to_md(desc.get_text() if desc else "")
        if not loc or not desc_md:
            html = get(link).text
            jp = jsonld_jobposting(html) or {}
            loc = loc or jsonld_location(jp)
            desc_md = desc_md or html_to_md(jp.get("description"))
        if not is_denmark(loc, "" if not cfg.get("dk_only") else "denmark"):
            continue
        jobs.append(Job(company=cfg["name"], title=title, url=link, location=loc,
                        description_md=desc_md, source="teamtailor", external_id=link.rstrip("/").split("/")[-1]))
    return listed, jobs

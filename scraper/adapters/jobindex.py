"""Jobindex RSS som supplerende kilde på tværs af alle virksomheder.

Bruges kun med simple søgeord (det robots.txt tillader). Hvert feed giver de ~20 nyeste
opslag, så kilden fanger løbende nye studenterjob hos virksomheder, hvis egen karriereside
ikke kan læses. Jobs matches til virksomhederne i companies.yaml via navn/aliaser.
"""
import re
from urllib.parse import quote

from bs4 import BeautifulSoup
from ..common import Job, get, soup, clean, html_to_md, is_student, find_deadline

QUERIES = ["studentermedhjælper", "student assistant", "studentermedarbejder", "studiejob", "student"]


def _matcher(companies):
    pats = []
    for c in companies:
        names = ([c["name"]] if c.get("match_name", True) else []) + c.get("aliases", [])
        # case-sensitive: undgår at fx "SAS" (software) eller "implement" matcher forkert
        rx = re.compile("|".join(r"(?<!\w)" + re.escape(n) + r"(?!\w)" for n in names))
        pats.append((c["name"], rx))
    return pats


def scrape_all(companies, today_year):
    """Returnerer (listed, [Job]) for alle virksomheder på én gang."""
    pats = _matcher(companies)
    seen, listed, jobs = set(), 0, []
    for q in QUERIES:
        try:
            xml = get(f"https://www.jobindex.dk/jobsoegning.rss?q={quote(q)}").text
        except Exception:
            continue
        for it in BeautifulSoup(xml, "xml").find_all("item"):
            link = clean(it.find("link").get_text() if it.find("link") else "") or \
                clean(it.find("guid").get_text() if it.find("guid") else "")
            if not link or link in seen:
                continue
            seen.add(link)
            listed += 1
            title = clean(it.find("title").get_text() if it.find("title") else "")
            d = it.find("description")
            dtxt = clean(BeautifulSoup(d.get_text(), "lxml").get_text(" ")) if d else ""
            blob = title + " | " + dtxt[:250]   # kun starten: virksomhedsnavnet står først, undgå fx "Microsoft 365" i brødteksten
            company = next((n for n, rx in pats if rx.search(blob)), None)
            if not company or not is_student(title + " " + blob[:300]):
                continue
            jid = re.search(r"(h\d+)", link)
            ad_url = f"https://www.jobindex.dk/jobannonce/{jid.group(1)}/" if jid else link
            desc_md, apply = "", link
            try:
                s = soup(get(ad_url).text)
                body = s.select_one(".jobtext-jobad__body, .PaidJob-inner, article, main")
                desc_md = html_to_md(str(body)) if body else ""
                a = s.select_one("a[href*='/c?t='], a.btn-apply, a[data-click*=apply]")
                if a:
                    apply = a["href"] if a["href"].startswith("http") else "https://www.jobindex.dk" + a["href"]
            except Exception:
                desc_md = html_to_md(str(it.find("description") or ""))
            jobs.append(Job(company=company, title=title, url=link, apply_url=apply, location="Danmark",
                            deadline=find_deadline(desc_md, today_year) or "", description_md=desc_md,
                            source="jobindex", external_id=jid.group(1) if jid else link))
    return listed, jobs


def scrape(cfg):  # ikke brugt pr. virksomhed
    return 0, []

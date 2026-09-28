"""Jobindex RSS som supplerende kilde på tværs af alle virksomheder.

Bruges kun med simple søgeord (det robots.txt tillader). Hvert feed giver de ~20 nyeste
opslag, så kilden fanger løbende nye studenterjob hos virksomheder, hvis egen karriereside
ikke kan læses. Jobs matches til virksomhederne i companies.yaml via navn/aliaser.
"""
import re
from urllib.parse import quote

from bs4 import BeautifulSoup
from ..common import Job, get, soup, clean, html_to_md, is_student, find_deadline, is_cph, topic_tags

QUERIES = ["studentermedhjælper", "student assistant", "studentermedarbejder", "studiejob", "student"]
# Feeds: (sti, søgeord). Stier udvides når robots.txt er tjekket. Hvert feed = de ~20 nyeste opslag.
FEEDS = [("jobsoegning", q) for q in QUERIES]


def _matcher(companies):
    pats = []
    for c in companies:
        names = ([c["name"]] if c.get("match_name", True) else []) + c.get("aliases", [])
        # case-sensitive: undgår at fx "SAS" (software) eller "implement" matcher forkert
        rx = re.compile("|".join(r"(?<!\w)" + re.escape(n) + r"(?!\w)" for n in names))
        pats.append((c["name"], rx))
    return pats


def scrape_all(companies, today_year, all_companies=True):
    """Returnerer (listed, [Job]).

    Top 50-virksomheder: alle studenterjob i Danmark.
    Andre virksomheder (all_companies=True): studenterjob i Storkøbenhavn med mindst ét fagligt match.
    """
    pats = _matcher(companies)
    seen, listed, jobs = set(), 0, []
    for path, q in FEEDS:
        try:
            xml = get(f"https://www.jobindex.dk/{path}.rss?q={quote(q)}").text
        except Exception:
            continue
        for it in BeautifulSoup(xml, "xml").find_all("item"):
            link = clean(it.find("link").get_text() if it.find("link") else "") or \
                clean(it.find("guid").get_text() if it.find("guid") else "")
            if not link or link in seen:
                continue
            seen.add(link)
            listed += 1
            full_title = clean(it.find("title").get_text() if it.find("title") else "")
            d = it.find("description")
            dsoup = BeautifulSoup(d.get_text(), "lxml") if d else None
            # RSS-titlen er "<jobtitel>, <virksomhed>"; logoets ALT er også virksomheden
            title, _, comp_txt = full_title.rpartition(", ")
            if not title:
                title, comp_txt = full_title, ""
            img = dsoup.find("img") if dsoup else None
            comp_txt = f"{comp_txt} | {img.get('alt', '') if img else ''}"
            company = next((n for n, rx in pats if rx.search(comp_txt)), None)
            top50 = company is not None
            if not top50 and all_companies:
                company = clean(comp_txt.split("|")[0]) or clean(img.get("alt", "") if img else "") or "Ukendt"
            teaser_html = ""
            loc = "Danmark"
            if dsoup:
                a = dsoup.select_one(".jix_robotjob--area, .jobad-element-area")
                loc = clean(a.get_text()) if a else loc
                ps = dsoup.find_all(["p", "ul"])
                teaser_html = "".join(str(x) for x in ps)
            teaser_txt = clean(dsoup.get_text(" "))[:600] if dsoup else ""
            if not company or not is_student(full_title + " " + teaser_txt):
                continue
            # uden for top 50: kun Storkøbenhavn og kun hvis titel/uddrag rammer dine fagområder
            if not top50 and not (is_cph(loc) and topic_tags(title, teaser_txt)):
                continue
            jid = re.search(r"(h\d+)", link)
            ad_url = f"https://www.jobindex.dk/jobannonce/{jid.group(1)}/" if jid else link
            desc_md, apply = "", link
            try:
                s2 = soup(get(ad_url).text)
                body = s2.select_one("article.jobcontent, .jobtext-jobad__body, .PaidJob-inner, article, main")
                if body:
                    for bad in body.select("nav, script, style, .rating, .jix-tags, footer"):
                        bad.decompose()
                    desc_md = html_to_md(str(body))
                a2 = s2.select_one("a[href*='/c?t=']")
                if a2:
                    apply = a2["href"] if a2["href"].startswith("http") else "https://www.jobindex.dk" + a2["href"]
            except Exception:
                pass
            if len(desc_md) < 300:
                desc_md = html_to_md(teaser_html) + "\n\n*(Kort uddrag fra Jobindex – se hele opslaget via linket.)*"
            jobs.append(Job(company=company, title=title, url=link, apply_url=apply, location=loc,
                            deadline=find_deadline(desc_md, today_year) or "", description_md=desc_md,
                            source="jobindex", external_id=jid.group(1) if jid else link, top50=top50))
    return listed, jobs


def scrape(cfg):  # ikke brugt pr. virksomhed
    return 0, []

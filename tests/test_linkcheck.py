"""Linkkontrol (2/11): døde opslag og karrieresider må ikke stå i appen."""
import scraper.linkcheck as L
import scraper.platform_run as P

ARLA = "https://jobs.arla.com/global/en/job/111024"
JYSKE = "https://www.jyskebank.dk/om-os/job-og-karriere/ledige-jobs/jobopslag?id=191425"


def page(title="", h1="", body="Studentermedhjælper til økonomi. Du får ansvar for rapportering og analyser. " * 3):
    return f"<html><head><title>{title}</title></head><body><main><h1>{h1}</h1><p>{body}</p></main></body></html>"


def test_classify_real_cases_from_2_november():
    # Jyske Bank: siden svarer 200, men titlen siger, at opslaget er væk
    assert L.classify(JYSKE, 200, JYSKE, page("Jobopslaget blev ikke fundet"))[0] == "dead"
    # Arla (Phenom): lukket opslag sender videre til forsiden for Storbritannien
    v = L.classify(ARLA, 200, "https://jobs.arla.com/gb/en", page("job openings at Arla Foods"))
    assert v[0] == "dead" and "viderestillet" in v[1]
    # Nordnet: karriereside med 404 (status 200 + titel, og ægte 404)
    nn = "https://www.nordnet.dk/dk/om-nordnet/karriere"
    assert L.classify(nn, 200, nn, page("404 Siden blev ikke fundet | Nordnet"), "page")[0] == "dead"
    assert L.classify(nn, 404, nn, "", "page")[0] == "dead"
    # Oracle: ansøgningsflowet sender til /404
    o = "https://ejqi.fa.ocs.oraclecloud.eu/hcmUI/CandidateExperience/en/sites/CX_1001/job/24975/apply"
    assert L.classify(o, 200, "https://ejqi.fa.ocs.oraclecloud.eu/hcmUI/CandidateExperience/en/sites/CX_1001/404", "")[0] == "dead"
    assert L.classify(ARLA, 200, ARLA, page("Studiejob", "Student", "This position is no longer available."))[0] == "dead"


def test_classify_live_pages_and_unknowns():
    # Tryg (SuccessFactors) skifter id i URL'en, men bliver på opslaget – ikke dødt
    t = "https://careers.tryg.com/Tryg/job/Ballerup-Studentermedhj%C3%A6lper-til-r%C3%A5dgivning-og-salg/1452951533/"
    t2 = "https://careers.tryg.com/Tryg/job/Ballerup-Studentermedhj%C3%A6lper-til-r%C3%A5dgivning-og-salg/28828-da_DK/"
    assert L.classify(t, 200, t2, page("Studentermedhjælper til rådgivning og salg"))[0] == "ok"
    # Workday-skal uden tekst: ok (kun status), og en bot-mur er "unknown", aldrig "dead"
    w = "https://saxobank.wd3.myworkdayjobs.com/CareeratSaxoBank/job/Headquarters/Student_R-19589"
    assert L.classify(w, 200, w, "<html><body><div id=root></div></body></html>")[0] == "ok"
    assert L.classify(JYSKE, 403, JYSKE, "")[0] == "unknown"
    assert L.classify(JYSKE, 503, JYSKE, "")[0] == "unknown"
    # "404" i brødteksten (fx en adresse) gør ikke siden død
    assert L.classify(JYSKE, 200, JYSKE, page("Student", "Student", "Postboks 404, 2300 København. Søg senest 1/12."))[0] == "ok"


def test_check_handles_errors_and_robots():
    def boom(url):
        raise TimeoutError
    assert L.check(JYSKE, fetcher=boom, robots=lambda u: True) == ("unknown", "TimeoutError")
    assert L.check(JYSKE, fetcher=boom, robots=lambda u: False)[0] == "unknown"


def _job(i, url, last_seen="2026-11-02T01:00:00+00:00", company="Jyske Bank"):
    return {"id": i, "company": company, "title": "Studentermedhjælper", "url": url, "apply_url": url, "active": True,
            "last_seen": last_seen, "career_url": "https://www.nordnet.dk/dk/om-nordnet/karriere",
            "source_employer": company}


def test_retire_dead_and_stale_jobs():
    now = "2026-11-02T08:00:00+00:00"
    jobs = {"a": _job("a", JYSKE), "b": _job("b", "https://x/ok", "2026-10-20T01:00:00+00:00"),
            "c": _job("c", "https://x/unknown", "2026-10-20T01:00:00+00:00"),
            "d": _job("d", "https://x/new"), "e": _job("e", "https://x/old-ok", "2026-10-10T01:00:00+00:00")}
    v = {JYSKE: ("dead", "titel: Jobopslaget blev ikke fundet"), "https://x/ok": ("ok", ""),
         "https://x/unknown": ("unknown", "HTTP 403"), "https://x/new": ("unknown", "Timeout"),
         "https://x/old-ok": ("ok", "")}
    out = P.retire_stale_and_dead(jobs, v, now)
    assert {r["id"] for r in out["dead"]} == {"a"}
    assert {r["id"] for r in out["stale"]} == {"c", "e"}         # c: 13 dage + ukendt, e: over 14 dage
    assert jobs["b"]["active"] and jobs["d"]["active"]           # b: set for 13 dage siden, men opslaget svarer ok


def test_run_linkcheck_replaces_dead_career_page():
    now = "2026-11-02T08:00:00+00:00"
    nn = "https://www.nordnet.dk/dk/om-nordnet/karriere"
    emps = [{"name": "Nordnet", "career_url": nn, "source": {"type": "teamtailor", "url": "https://career.nordnetab.com"}},
            {"name": "Jyske Bank", "career_url": "https://www.jyskebank.dk/job",
             "source": {"type": "generic", "list_urls": ["https://www.jyskebank.dk/job"]}}]
    jobs = {"a": _job("a", JYSKE, company="Nordnet")}
    pages = {nn: (404, nn, ""), JYSKE: (200, JYSKE, page("Jobopslaget blev ikke fundet")),
             "https://career.nordnetab.com/jobs": (200, "https://career.nordnetab.com/jobs", page("Our jobs"))}
    rep = P.run_linkcheck(jobs, emps, now, fetcher=lambda u: pages.get(u, (200, u, page("ok"))))
    assert emps[0]["career_url"] == "https://career.nordnetab.com/jobs"
    assert emps[0]["domain"] == "nordnet.dk"                     # logoet beholdes
    assert jobs["a"]["career_url"] == "https://career.nordnetab.com/jobs" and not jobs["a"]["active"]
    assert rep["career_dead"][0]["company"] == "Nordnet" and rep["jobs_dead"][0]["id"] == "a"
    assert emps[1]["career_url"] == "https://www.jyskebank.dk/job"

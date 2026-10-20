"""Platform-kørslen (Jobradar): jobtyper, region, nøgleord, kontrakt og at Jobindex aldrig kommer med."""
import json

import pytest
import yaml

import scraper.common as C
import scraper.platform_run as P
from scraper.common import Job


@pytest.fixture(autouse=True)
def reset_mode():
    yield
    C.set_job_types({"studiejob"})          # andre tests forventer den personlige tilstand
    C.set_topics(C.TOPICS)


@pytest.fixture
def rx():
    return P.compile_keywords(P.load_keywords())


@pytest.mark.parametrize("title,expected", [
    ("Studentermedhjælper til Group Finance", "studiejob"),
    ("Summer Internship 2027 – Finance", "praktik"),
    ("Praktikant i Kommunikation", "praktik"),
    ("Graduate Programme – Technology", "graduate"),
    ("Trainee i Jura", "graduate"),
    ("PhD Student in Economics", None),
    ("Senior Graduate Recruiter", None),
    ("Speciale-studerende søges", None),
])
def test_job_type(title, expected):
    assert C.job_type(title) == expected


def test_personal_mode_still_excludes_praktik():
    C.set_job_types({"studiejob"})
    assert C.student_fit("Praktikant i Marketing") is None
    C.set_job_types(P.JOB_TYPES)
    assert C.student_fit("Praktikant i Marketing") == "sikker"
    assert C.is_student("Graduate Analyst")


def test_keywords_danish_and_english(rx):
    da = P.match_keywords(rx, "Studentermedhjælper", "Du skal arbejde med dataanalyse i SQL og automatisering")
    en = P.match_keywords(rx, "Student Assistant", "You will work with data analysis in SQL and automation")
    assert {"data-analyse", "sql", "automatisering"} <= set(da)
    assert {"data-analyse", "sql", "automatisering"} <= set(en)


def test_keywords_jura(rx):
    k = P.match_keywords(rx, "Juridisk studentermedhjælper", "Opgaver inden for GDPR, kontrakter og hvidvask (AML)")
    assert {"jura", "gdpr", "kontraktret", "hvidvask", "legal-assistant"} <= set(k)


def test_company_name_does_not_create_keywords(rx):
    k = P.match_keywords(rx, "Student Assistant", "Hos Danske Bank arbejder du med marketing", company="Danske Bank")
    assert "bank" not in k and "marketing" in k


def test_study_lines_reference_known_keywords():
    ids = {k["id"] for k in P.load_keywords()}
    for line in P.load_study_lines():
        assert 5 <= len(line["suggested"]) <= 15
        assert set(line["suggested"]) | set(line["avoid"]) <= ids


def test_employers_file_is_sane():
    emps = P.load_employers()
    names = [e["name"] for e in emps]
    assert len(names) == len(set(names)) and len(emps) >= 100
    for e in emps:
        assert "lines" not in e          # 13/10: ingen arbejdsgiver mærkes med én studieretning
        assert (e.get("source") or {}).get("type") != "jobindex"


def emp(**kw):
    return {"name": "Tryg", "lines": ["ha-almen"], "career_url": "https://careers.tryg.com", **kw}


def test_build_record_region_and_type(rx):
    j = Job(company="Tryg", title="Studentermedhjælper til Compliance", url="https://careers.tryg.com/job/1",
            location="Ballerup", description_md="Du arbejder med compliance og GDPR", source="successfactors").to_dict()
    r = P.build_record(j, emp(), rx, "2026-10-13T00:00:00+00:00")
    assert r["job_type"] == "studiejob" and r["region"] == "storkbh" and "compliance" in r["keywords"]
    j2 = dict(j, location="Aarhus C")
    assert P.build_record(j2, emp(), rx, "x") is None


def test_merge_state_marks_missing_jobs_inactive():
    old = {"a": {"id": "a", "company": "Tryg", "first_seen": "2026-10-01T00:00:00+00:00", "last_seen": "2026-10-12T00:00:00+00:00", "active": True},
           "b": {"id": "b", "company": "Ukendt AS", "first_seen": "2026-10-01T00:00:00+00:00", "last_seen": "2026-10-12T00:00:00+00:00", "active": True}}
    out = P.merge_state({}, old, {"Tryg"}, "2026-10-13T00:00:00+00:00", "2026-10-13")
    assert out["a"]["active"] is False      # kilden virkede, jobbet er væk
    assert out["b"]["active"] is True       # kilden fejlede: behold


def test_validate_rejects_jobindex_and_unknown_keywords(rx):
    base = {"id": "x1", "company": "A", "title": "Student", "job_type": "studiejob", "region": "storkbh", "keywords": [],
            "lines": [], "active": True, "first_seen": "2026-10-13", "description_md": "", "apply_url": "https://a/1"}
    ok = {"schema_version": 2, "jobs": [base]}
    assert P.validate(ok, set(rx)) == []
    assert P.validate({"schema_version": 2, "jobs": [dict(base, source="jobindex")]}, set(rx))
    assert P.validate({"schema_version": 2, "jobs": [dict(base, keywords=["findes-ikke"])]}, set(rx))


def test_main_end_to_end_with_fake_adapter(tmp_path, monkeypatch):
    def fake(cfg):
        assert "intern" in cfg["search_terms"]          # platform-søgeord sendes med
        return 3, [Job(company=cfg["name"], title="Student Assistant – Data", url="https://x/1", location="København",
                       description_md="SQL og Power BI", source="workday", external_id="1"),
                   Job(company=cfg["name"], title="Internship – Legal", url="https://x/2", location="Copenhagen",
                       description_md="contracts and compliance", source="workday", external_id="2"),
                   Job(company=cfg["name"], title="Student Assistant", url="https://x/3", location="Aarhus",
                       source="workday", external_id="3")]
    plat = tmp_path / "platform"
    plat.mkdir()
    for f in ("keywords.yaml", "study_lines.yaml"):
        (plat / f).write_text((P.PLAT / f).read_text())
    (plat / "employers.yaml").write_text(yaml.safe_dump({"employers": [
        {"name": "Testfirma", "lines": ["ha-it"], "career_url": "https://x", "status": "klar", "source": {"type": "workday", "url": "https://x"}}]}))
    monkeypatch.setattr(P, "PLAT", plat)
    monkeypatch.setattr(P, "OUT", tmp_path / "out")
    monkeypatch.setitem(P.ADAPTERS, "workday", fake)
    P.main([])
    data = json.loads((tmp_path / "out" / "jobs.json").read_text())
    types = sorted(j["job_type"] for j in data["jobs"])
    assert data["schema_version"] == 2 and types == ["praktik", "studiejob"]   # Aarhus-jobbet er filtreret fra
    assert json.loads((tmp_path / "out" / "keywords.json").read_text())["keywords"][0].get("pattern") is None


def test_boilerplate_mentioned_once_is_ignored(rx):
    body = ("Som studentermedhjælper laver du dataanalyse i Excel og hjælper teamet med rapporter. " * 4
            + "Om os: Vi er en stor organisation med mange dygtige kolleger. " * 3
            + "Vi tilbyder fleksible arbejdstider, frokostordning og pension.")
    k = P.match_keywords(rx, "Student Assistant", body)
    assert "data-analyse" in k and "forsikring" not in k


@pytest.mark.parametrize("title", ["Laborantpraktikant til molekylærbiologi", "Kontorelev i HR", "Elev til regnskab"])
def test_vocational_roles_are_not_platform_jobs(title):
    assert C.job_type(title) is None


@pytest.mark.parametrize("title,expected", [
    ("Deloitte SAP Graduate Dinner 2026 — December 3rd", None),
    ("Student Event: Join Our Digital Transformation Programme", None),
    ("Step Inside Accenture: An Evening for IT Students", None),
    ("Drømmer du om at arbejde med events? Bliv Employer Branding-praktikant i PwC", "praktik"),
])
def test_events_are_not_jobs(title, expected):
    assert C.job_type(title) == expected


def test_parttime_without_topic_in_title_is_dropped(rx):
    base = {"company": "Novonesis", "url": "https://x/1", "location": "Bagsværd", "source": "workday", "id": "x1", "fit": "mulig"}
    lab = dict(base, title="Laboratory Technician (part-time)", description_md="Du arbejder 15 timer om ugen med data og analyse")
    analyst = dict(base, title="Analyst (part-time) - Corporate Finance", description_md="15 timer om ugen")
    assert P.build_record(lab, emp(), rx, "x") is None
    assert P.build_record(analyst, emp(), rx, "x")["job_type"] == "studiejob"


def test_company_domain_from_career_page_and_override():
    from scraper.platform_run import company_domain
    assert company_domain({"career_url": "https://careers.bcg.com/x"}) == "bcg.com"
    assert company_domain({"career_url": "https://www.pfa.dk/om-pfa/job/"}) == "pfa.dk"
    assert company_domain({"career_url": "https://candidate.hr-manager.net/x"}) is None
    assert company_domain({"career_url": "https://x.wd3.myworkdayjobs.com/", "domain": "svitzer.com"}) == "svitzer.com"


def test_employer_region_fills_unknown_location():
    from scraper.platform_run import build_record, compile_keywords, load_keywords
    from scraper.common import set_job_types
    set_job_types({"studiejob", "praktik", "graduate"})
    rx = compile_keywords(load_keywords())
    job = {"id": "x1", "company": "EY", "title": "Student Assistant - Valuation", "location": "Danmark",
           "description_md": "Student assistant 15-20 hours a week", "fit": "sikker"}
    assert build_record(job, {"region": "storkbh"}, rx, "2026-10-13")["region"] == "storkbh"
    assert build_record(job, {}, rx, "2026-10-13")["region"] == "ukendt"


def test_merge_state_shared_portal_uses_source_employer():
    """Job fra en fælles portal har firmanavnet fra opslaget (fx Banedanmark), men kilden er portalen.
    Forsvinder jobbet, og portalen virkede, skal det lukkes, selvom firmanavnet ikke er en kilde."""
    old = {"a": {"id": "a", "company": "Banedanmark", "source_employer": "Statens Rekrutteringsløsning",
                 "first_seen": "2026-10-01T00:00:00+00:00", "last_seen": "2026-10-14T00:00:00+00:00", "active": True}}
    import copy
    out = P.merge_state({}, copy.deepcopy(old), {"Statens Rekrutteringsløsning"}, "2026-10-15T00:00:00+00:00", "2026-10-15")
    assert out["a"]["active"] is False
    out = P.merge_state({}, copy.deepcopy(old), {"Andre"}, "2026-10-15T00:00:00+00:00", "2026-10-15")
    assert out["a"]["active"] is True


def test_employer_list_expands_shared_portal():
    employers = [{"name": "Statens Rekrutteringsløsning", "career_url": "https://x", "status": "klar",
                  "source": {"type": "hrmanager", "customer": "statensrekrutteringsloesning_tr"}},
                 {"name": "Finanstilsynet", "career_url": "https://www.finanstilsynet.dk/job", "status": "find-system",
                  "source": {"type": "none"}},
                 {"name": "KPMG", "career_url": "https://kpmg.dk", "status": "klar", "source": {"type": "hrmanager"}}]
    jobs = [{"company": "Banedanmark", "source_employer": "Statens Rekrutteringsløsning", "active": True},
            {"company": "Finanstilsynet", "source_employer": "Statens Rekrutteringsløsning", "active": True},
            {"company": "Lukket Styrelse", "source_employer": "Statens Rekrutteringsløsning", "active": False},
            {"company": "KPMG", "source_employer": "KPMG", "active": True}]
    names = [e["name"] for e in P.employer_list(employers, jobs, {})]
    assert "Statens Rekrutteringsløsning" not in names        # portalen selv vises ikke
    assert "Banedanmark" in names and names.count("Finanstilsynet") == 1   # kendt navn genbruges, ingen dublet
    assert "Lukket Styrelse" not in names and "KPMG" in names


def test_employer_list_portal_status_and_outside_region():
    employers = [{"name": "Statens Rekrutteringsløsning", "status": "klar", "source": {"type": "hrmanager"}},
                 {"name": "Skatteministeriet og Skattestyrelsen", "status": "via-portal", "source": {"type": "none"},
                  "aliases": ["Skatte- og Vækstministeriet"]},
                 {"name": "Datatilsynet", "status": "via-portal", "source": {"type": "none"}},
                 {"name": "Würth Danmark A/S", "region": "udenfor", "status": "opdaget", "source": {"type": "emply"}}]
    jobs = [{"company": "Skatte- og Vækstministeriet", "source_employer": "Statens Rekrutteringsløsning", "active": True},
            {"company": "Skatte- og Vækstministeriet", "source_employer": "Statens Rekrutteringsløsning", "active": True}]
    rows = {e["name"]: e for e in P.employer_list(employers, jobs, {})}
    skm = rows["Skatteministeriet og Skattestyrelsen"]
    assert skm["status"] == "klar" and skm["via"] == "Statens Rekrutteringsløsning" and skm["matched"] == 2
    assert skm["source_type"] == "hrmanager"
    assert rows["Datatilsynet"]["status"] == "via-portal"       # ingen aktive job lige nu
    assert "Würth Danmark A/S" not in rows                       # uden for Sjælland vises ikke
    assert "Skatte- og Vækstministeriet" not in rows             # alias → ingen dublet-række


def test_rejected_report(tmp_path):
    rej = [{"company": "Novo", "title": "Senior Scientist", "reason": "ikke studiejob", "url": "u1"},
           {"company": "Novo", "title": "Student i Kalundborg", "reason": "uden for Sjælland (Aarhus)", "url": "u2"},
           {"company": "Novo", "title": "Student 2", "reason": "uden for Sjælland (Odense)", "url": ""}]
    P.write_rejected(tmp_path / "r.json", rej)
    import json
    d = json.loads((tmp_path / "r.json").read_text())["companies"]["Novo"]
    assert d["count"] == 3 and d["reasons"] == {"ikke studiejob": 1, "uden for Sjælland": 2}
    assert d["examples"][2] == {"title": "Student 2", "reason": "uden for Sjælland (Odense)"}


def test_why_rejected():
    assert P.why_rejected({"title": "Senior Manager", "description_md": "", "location": "København"}, {}) \
        .startswith("ikke studiejob")
    assert P.why_rejected({"title": "Studentermedhjælper", "description_md": "", "location": "Aarhus"}, {}) \
        .startswith("uden for Sjælland")


def test_employer_reading_is_honest():
    """20/10: arbejdsgivere, der står på listen, men hvis kilde aldrig har givet opslag, skal stå som "læses ikke endnu"."""
    now = "2026-10-20T06:00:00+00:00"
    employers = [{"name": "Statens Rekrutteringsløsning (staten)", "status": "klar",
                  "source": {"type": "hrmanager", "multi_employer": True}},
                 {"name": "Coloplast", "status": "klar", "source": {"type": "sitemap"}},
                 {"name": "Bech-Bruun", "status": "klar", "source": {"type": "emply"}},
                 {"name": "DR", "status": "klar", "source": {"type": "hrmanager"}},
                 {"name": "Gammel kilde", "status": "klar", "source": {"type": "workday"}},
                 {"name": "McKinsey", "status": "find-system", "source": {"type": "none"}},
                 {"name": "Datatilsynet", "status": "via-portal", "source": {"type": "none"}}]
    sources = {"Statens Rekrutteringsløsning (staten)": {"last_data": now},
               "Coloplast": {"ok": True, "listed": 290, "last_data": now},
               "Bech-Bruun": {"ok": True, "listed": 0, "last_data": None},
               "DR": {"ok": True, "listed": 0, "last_data": "2026-10-05T06:00:00+00:00"},       # 0 opslag lige nu
               "Gammel kilde": {"ok": False, "last_data": "2026-08-01T06:00:00+00:00"}}         # død i 2½ måned
    rows = {r["name"]: r for r in P.employer_list(employers, [], sources, now)}
    assert rows["Coloplast"]["reading"] == "læses" and rows["Coloplast"]["last_data"] == "2026-10-20"
    assert rows["DR"]["reading"] == "læses"
    assert rows["Bech-Bruun"]["reading"] == "læses-ikke-endnu"
    assert rows["Gammel kilde"]["reading"] == "læses-ikke-endnu"
    assert rows["McKinsey"]["reading"] == "læses-ikke-endnu"
    assert rows["Datatilsynet"]["reading"] == "læses" and rows["Datatilsynet"]["via"] == "Statens Rekrutteringsløsning (staten)"


def test_data_since():
    now = "2026-10-20T06:00:00+00:00"
    assert P.data_since({"ok": True, "listed": 5}, {}, now) == now
    assert P.data_since({"ok": True, "listed": 0}, {"last_data": "2026-10-01"}, now) == "2026-10-01"
    assert P.data_since({"ok": True, "listed": 0}, {"listed": 16}, now) == now        # overgang fra gammel tilstand
    assert P.data_since({"ok": False}, {}, now) is None
    assert P.data_since({"ok": True, "listed": 0}, {"listed": 0}, now) is None

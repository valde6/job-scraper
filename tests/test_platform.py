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
        assert set(e["lines"]) <= {"ha-it", "ha-almen", "ha-jura"} and e["lines"]
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

"""Kontrakten mellem scraperen og appen (data/platform/jobs.json)."""
import json
from pathlib import Path

import pytest

from scraper.export import to_platform_job, validate_payload, SCHEMA_VERSION

ROOT = Path(__file__).resolve().parent.parent


def job(**kw):
    base = {"id": "abc123def456", "company": "LEGO Group", "title": "Student Assistant", "url": "https://x/1",
            "apply_url": "", "location": "Billund", "deadline": "2026-11-01", "posted": "", "source": "workday",
            "tags": ["Data & analyse"], "description_md": "Tekst", "active": True, "first_seen": "2026-10-01T00:00:00+00:00",
            "last_seen": "2026-10-02T00:00:00+00:00"}
    base.update(kw)
    return base


def payload(*jobs):
    return {"schema_version": SCHEMA_VERSION, "jobs": [to_platform_job(j, {"LEGO Group": 4}) for j in jobs]}


def test_valid_job():
    p = payload(job())
    assert validate_payload(p) == []
    j = p["jobs"][0]
    assert j["origin"] == "employer" and j["rank"] == 4 and j["posted"] is None and j["fit"] == "sikker"


def test_jobindex_origin():
    assert payload(job(source="jobindex"))["jobs"][0]["origin"] == "jobindex"


@pytest.mark.parametrize("bad", [{"title": ""}, {"url": "not-a-url"}, {"deadline": "15. oktober"}, {"fit": "måske"}])
def test_invalid_jobs_are_caught(bad):
    assert validate_payload(payload(job(**bad)))


def test_duplicate_ids_caught():
    assert any("dubleret" in e for e in validate_payload(payload(job(), job())))


def test_committed_export_is_valid():
    f = ROOT / "data" / "platform" / "jobs.json"
    if not f.exists():
        pytest.skip("ingen eksport endnu")
    assert validate_payload(json.loads(f.read_text())) == []


def test_export_excludes_jobindex(tmp_path, monkeypatch):
    import scraper.export as E
    monkeypatch.setattr(E, "OUT", tmp_path)
    p = E.export_platform([job(), job(id="zzz999zzz999", source="jobindex", url="https://x/2")], [], [], "2026-10-12T00:00:00+00:00")
    assert [j["origin"] for j in p["jobs"]] == ["employer"]

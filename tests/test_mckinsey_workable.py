"""McKinsey (eget JSON-API) og Workable. Svarene er forkortede udgaver af de rigtige svar set 20/10."""
from types import SimpleNamespace

import pytest

from scraper.adapters import mckinsey, workable
from scraper.common import set_job_types


@pytest.fixture(autouse=True)
def _types():
    set_job_types({"studiejob", "praktik", "graduate"})


class _R(SimpleNamespace):
    def json(self):
        return self.data


MCK = {"numFound": 3, "start": 0, "httpStatus": "OK", "docs": [
    {"jobID": "15275", "title": "Business Analyst Intern", "friendlyURL": "businessanalystintern-15275",
     "jobApplyURL": "https://mckinsey.avature.net/careers/ApplicationMethods?folderId=15275",
     "whatYouWillDo": "<div>As a business analyst intern, you will join a client service team for 8-10 weeks.</div>",
     "yourBackground": "<ul><li>Undergraduate degree in progress.</li></ul>"},
    {"jobID": "15178", "title": "Associate", "friendlyURL": "associate-15178",
     "whatYouWillDo": "<div>You will lead teams of consultants.</div>"},
    {"jobID": "112305", "title": "Senior Executive Assistant", "friendlyURL": "seniorexecutiveassistant-112305",
     "whatYouWillDo": "<div>Support partners.</div>"},
]}


def test_mckinsey(monkeypatch):
    urls = []

    def get(url, **kw):
        urls.append(url)
        return _R(data=MCK)
    monkeypatch.setattr(mckinsey, "get", get)
    monkeypatch.setattr(mckinsey, "robots_allows", lambda u: True)
    listed, jobs = mckinsey.scrape({"name": "McKinsey & Company"})
    assert listed == 3 and len(urls) == 1 and "cities=Copenhagen" in urls[0]
    assert [j.title for j in jobs] == ["Business Analyst Intern"]
    j = jobs[0]
    assert j.url == "https://www.mckinsey.com/careers/search-jobs/jobs/businessanalystintern-15275"
    assert j.apply_url.startswith("https://mckinsey.avature.net/") and j.location == "Copenhagen"
    assert "Undergraduate degree in progress" in j.description_md


WK_LIST = {"results": [
    {"id": 1, "shortcode": "AAA111", "title": "Student Assistant, Grant Management", "published": "2026-10-20T00:00:00.000Z",
     "location": {"city": "Hellerup", "country": "Denmark", "countryCode": "DK"}},
    {"id": 2, "shortcode": "BBB222", "title": "Clinical Immunologist",
     "location": {"city": "Copenhagen", "country": "Denmark", "countryCode": "DK"}},
    {"id": 3, "shortcode": "CCC333", "title": "Student Assistant", "location": {"city": "Boston", "countryCode": "US"}},
]}
WK_DETAIL = {"AAA111": {"description": "<p>Student assistant 15 hours per week alongside your studies.</p>"},
             "BBB222": {"description": "<p>Senior clinical role.</p>"}}


def test_workable(monkeypatch):
    got = []
    monkeypatch.setattr(workable, "post", lambda url, **kw: _R(data=WK_LIST))

    def get(url, **kw):
        got.append(url)
        return _R(data=WK_DETAIL[url.rsplit("/", 1)[1]])
    monkeypatch.setattr(workable, "get", get)
    listed, jobs = workable.scrape({"name": "Novo Nordisk Fonden", "account": "novonordiskfoundation"})
    assert listed == 3
    assert [j.title for j in jobs] == ["Student Assistant, Grant Management"]
    assert jobs[0].url == "https://apply.workable.com/novonordiskfoundation/j/AAA111/"
    assert jobs[0].location == "Hellerup, Denmark" and jobs[0].posted == "2026-10-20"
    assert not any("CCC333" in u for u in got)                       # udenlandske opslag hentes ikke

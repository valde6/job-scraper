"""Workday: stednavne uden by (Saxo Bank: "Headquarters") og ventetid ved 429 (Accenture)."""
from types import SimpleNamespace

import requests

from scraper import common
from scraper.adapters import workday


class _Resp(SimpleNamespace):
    def json(self):
        return self.data


def _fake(listing, details):
    calls = []

    def post(url, **kw):
        calls.append(("POST", kw["json"]["searchText"]))
        posts = listing if kw["json"]["offset"] == 0 and kw["json"]["searchText"] == "student" else []
        return _Resp(data={"total": len(posts), "jobPostings": posts})

    def get(url, **kw):
        calls.append(("GET", url))
        return _Resp(data={"jobPostingInfo": details[url.rsplit("/job/", 1)[1]]})
    return post, get, calls


LISTING = [
    {"title": "Student Digital Sales Associate", "externalPath": "/job/Headquarters/Student-Digital-Sales_R1",
     "locationsText": "Headquarters"},
    {"title": "Student Assistant - Digital Czech Language Support", "externalPath": "/job/Prague/Student-CZ_R2",
     "locationsText": "Prague"},
]
DETAILS = {
    "Headquarters/Student-Digital-Sales_R1": {"country": {"descriptor": "Denmark"}, "location": "Headquarters",
                                              "jobDescription": "<p>Student assistant 15-20 hours per week alongside your studies in sales.</p>",
                                              "jobReqId": "R1", "externalUrl": "https://x/job/R1"},
}


def test_location_map_keeps_headquarters_jobs(monkeypatch):
    post, get, calls = _fake(LISTING, DETAILS)
    monkeypatch.setattr(workday, "post", post)
    monkeypatch.setattr(workday, "get", get)
    cfg = {"name": "Saxo Bank", "url": "https://saxobank.wd3.myworkdayjobs.com/CareeratSaxoBank",
           "search_terms": ["student"], "location_map": {"Headquarters": "Hellerup"}}
    listed, jobs = workday.scrape(cfg)
    assert listed == 2
    assert [j.title for j in jobs] == ["Student Digital Sales Associate"]
    assert jobs[0].location == "Hellerup"
    assert not any("Prague" in str(c) for c in calls if c[0] == "GET")       # udlandet hentes ikke


def test_without_location_map_headquarters_is_skipped_and_logged(monkeypatch):
    post, get, _ = _fake(LISTING, DETAILS)
    monkeypatch.setattr(workday, "post", post)
    monkeypatch.setattr(workday, "get", get)
    common.REJECTED.clear()
    listed, jobs = workday.scrape({"name": "Saxo Bank", "url": "https://saxobank.wd3.myworkdayjobs.com/CareeratSaxoBank",
                                   "search_terms": ["student"]})
    assert jobs == []
    assert any(r["reason"].startswith("uden for Danmark (Headquarters") for r in common.REJECTED)


def test_retry_wait_respects_retry_after():
    r = requests.Response()
    r.status_code = 429
    r.headers["Retry-After"] = "12"
    assert common._retry_wait(r, 0) == 12
    r.headers["Retry-After"] = "999"
    assert common._retry_wait(r, 0) == 30
    del r.headers["Retry-After"]
    assert common._retry_wait(r, 1) == 10
    r.status_code = 503
    assert common._retry_wait(r, 1) == 5

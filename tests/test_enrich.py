"""AI-struktureringen testes uden netværk med en falsk model."""
import json

import scraper.enrich as E


def fake_ok(job, key):
    return E.clean_details({"language": "da", "summary": "  Du hjælper finansteamet. ", "tasks": ["Rapporter", ""],
                            "requirements": ["HA-studerende"], "contacts": [{"name": "Anna Hansen", "phone": "12345678"}, {"name": ""}],
                            "deadline": "2026-11-01"})


def jobs():
    return [{"id": "a1", "active": True, "title": "Student", "description_md": "Tekst"},
            {"id": "b2", "active": False, "title": "Gammel", "description_md": "Tekst"}]


def test_enrich_uses_cache_and_skips_inactive(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "CACHE", tmp_path)
    calls = []
    js = jobs()
    s1 = E.enrich_jobs(js, api_key="k", caller=lambda j, k: calls.append(j["id"]) or fake_ok(j, k))
    assert s1["new"] == 1 and calls == ["a1"] and "details" not in js[1]
    assert js[0]["details"]["summary"] == "Du hjælper finansteamet."
    assert js[0]["details"]["tasks"] == ["Rapporter"] and js[0]["details"]["contacts"] == [{"name": "Anna Hansen", "phone": "12345678"}]
    js2 = jobs()
    s2 = E.enrich_jobs(js2, api_key="k", caller=lambda j, k: calls.append(j["id"]) or fake_ok(j, k))
    assert s2["cached"] == 1 and calls == ["a1"]           # ingen nyt kald
    js3 = jobs(); js3[0]["description_md"] = "Ny tekst"
    E.enrich_jobs(js3, api_key="k", caller=lambda j, k: calls.append(j["id"]) or fake_ok(j, k))
    assert calls == ["a1", "a1"]                            # ændret tekst → nyt kald


def test_no_key_skips(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "CACHE", tmp_path)
    js = jobs()
    assert E.enrich_jobs(js, api_key="")["skipped_no_key"] == 1 and "details" not in js[0]


def test_failures_do_not_stop(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "CACHE", tmp_path)
    def boom(j, k):
        raise RuntimeError("api nede")
    assert E.enrich_jobs(jobs(), api_key="k", caller=boom)["failed"] == 1


def test_call_claude_parses_tool_use(monkeypatch):
    class R:
        status_code = 200
        def raise_for_status(self): pass
        def json(self):
            return {"content": [{"type": "tool_use", "name": "save_job",
                                 "input": {"language": "en", "summary": "Support the team", "tasks": ["Excel"], "requirements": []}}]}
    sent = {}
    def post(url, json=None, timeout=None, headers=None):
        sent.update(json)
        return R()
    monkeypatch.setattr(E.requests, "post", post)
    d = E.call_claude({"title": "Student", "company": "A", "description_md": "x"}, "key")
    assert d == {"language": "en", "summary": "Support the team", "tasks": ["Excel"]}
    assert sent["tool_choice"]["name"] == "save_job" and sent["model"] == E.MODEL

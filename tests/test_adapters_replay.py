"""Afspiller optagede HTTP-svar (tests/fixtures/<virksomhed>/http) gennem adapteren uden netværk.

Fejler testen, har en kodeændring ændret, hvad adapteren udleder af de samme rå data.
Er ændringen tilsigtet: optag på ny med `python -m scraper.record --only "<navn>"` (GitHub Action: record-fixtures).
"""
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures"
CASES = sorted(p for p in FIX.glob("*/expected.json")) if FIX.exists() else []


@pytest.mark.parametrize("exp_file", CASES, ids=[p.parent.name for p in CASES])
def test_adapter_replay(exp_file, monkeypatch):
    from scraper.adapters import ADAPTERS
    exp = json.loads(exp_file.read_text())
    companies = {c["name"]: c for c in yaml.safe_load((ROOT / "companies.yaml").read_text())["companies"]}
    c = companies[exp["company"]]
    monkeypatch.setenv("SCRAPER_REPLAY", str(exp_file.parent / "http"))
    listed, jobs = ADAPTERS[c["source"]["type"]]({**c["source"], "name": c["name"]})
    got = sorted(({"id": j.id, "title": j.title, "fit": j.fit, "deadline": j.deadline} for j in jobs), key=lambda x: x["id"])
    assert listed == exp["listed"]
    assert got == exp["jobs"]
    for j in jobs:                                    # basale krav til hvert job
        assert j.title.strip() and j.url.startswith("http") and j.company == c["name"]


def test_fixtures_exist_note():
    if not CASES:
        pytest.skip("Ingen fixtures optaget endnu – kør GitHub Action 'record-fixtures'")

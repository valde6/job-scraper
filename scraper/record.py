"""Optager test-fixtures: kører én virksomhed pr. adapter-type mod de rigtige sider og gemmer alle HTTP-svar.

Bagefter kan testene afspille svarene uden netværk (tests/test_adapters_replay.py) og tjekke, at adapteren
stadig giver præcis det samme resultat. Kør igen, når en side har ændret sig og adapteren er rettet.

    python -m scraper.record                    # én virksomhed pr. type
    python -m scraper.record --only "LEGO Group"
Køres i GitHub Actions (record-fixtures.yml), fordi job-siderne ikke kan nås alle steder fra.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures"
SKIP_TYPES = {"browser", "none", "jobindex"}   # browser-sider kan ikke optages via HTTP


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def pick(companies, only=None):
    seen, out = set(), []
    for c in companies:
        typ = (c.get("source") or {}).get("type", "none")
        if only:
            if c["name"] in only:
                out.append(c)
            continue
        if typ in SKIP_TYPES or typ in seen:
            continue
        seen.add(typ)
        out.append(c)
    return out


def record_one(c) -> dict:
    from .adapters import ADAPTERS
    d = FIX / slug(c["name"])
    if d.exists():
        shutil.rmtree(d)
    (d / "http").mkdir(parents=True)
    os.environ["SCRAPER_RECORD"] = str(d / "http")
    try:
        src = c["source"]
        listed, jobs = ADAPTERS[src["type"]]({**src, "name": c["name"]})
    finally:
        os.environ.pop("SCRAPER_RECORD", None)
    exp = {"company": c["name"], "type": c["source"]["type"], "listed": listed,
           "jobs": sorted(({"id": j.id, "title": j.title, "fit": j.fit, "deadline": j.deadline} for j in jobs),
                          key=lambda x: x["id"])}
    (d / "expected.json").write_text(json.dumps(exp, ensure_ascii=False, indent=1))
    return exp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", action="append")
    args = ap.parse_args()
    companies = yaml.safe_load((ROOT / "companies.yaml").read_text())["companies"]
    for c in pick(companies, args.only):
        try:
            exp = record_one(c)
            print(f"OK   {c['name']:<30} {exp['type']:<15} listed={exp['listed']} jobs={len(exp['jobs'])}")
        except Exception as e:  # noqa: BLE001
            print(f"FEJL {c['name']:<30} {type(e).__name__}: {str(e)[:200]}")
            shutil.rmtree(FIX / slug(c["name"]), ignore_errors=True)


if __name__ == "__main__":
    main()

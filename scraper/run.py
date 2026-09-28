"""Kører alle kilder og opdaterer data/jobs.json, data/new.json og data/status.json.

    python -m scraper.run                 # alle virksomheder
    python -m scraper.run --only "LEGO Group"
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import traceback
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

from .adapters import ADAPTERS
from .adapters import jobindex
from .common import topic_tags, find_deadline

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9æøå]+", " ", t.lower()).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", action="append")
    args = ap.parse_args()

    companies = yaml.safe_load((ROOT / "companies.yaml").read_text())["companies"]
    today = date.today()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    DATA.mkdir(exist_ok=True)

    old = {}
    if (DATA / "jobs.json").exists():
        old = {j["id"]: j for j in json.loads((DATA / "jobs.json").read_text())["jobs"]}

    found, status, ok_companies = [], [], set()
    for c in companies:
        if args.only and c["name"] not in args.only:
            continue
        src = c.get("source") or {}
        typ = src.get("type", "none")
        t0 = time.time()
        entry = {"company": c["name"], "rank": c.get("rank"), "source": typ}
        if typ not in ADAPTERS or typ == "jobindex":
            entry.update(ok=None, note="Ingen direkte kilde. Dækkes via Jobindex.")
            status.append(entry)
            continue
        try:
            listed, jobs = ADAPTERS[typ]({**src, "name": c["name"]})
            found += jobs
            ok_companies.add(c["name"])
            entry.update(ok=True, listed=listed, matched=len(jobs))
        except Exception as e:  # noqa: BLE001
            entry.update(ok=False, error=f"{type(e).__name__}: {str(e)[:300]}")
            traceback.print_exc(file=sys.stderr)
        entry["seconds"] = round(time.time() - t0, 1)
        print(f"{c['name']:<32} {typ:<15} {entry.get('ok')} {entry.get('listed', '')} {entry.get('matched', '')} {entry.get('error', '')}")
        status.append(entry)

    if not args.only:
        try:
            listed, jobs = jobindex.scrape_all(companies, today.year)
            found += jobs
            status.append({"company": "(Jobindex RSS)", "source": "jobindex", "ok": True, "listed": listed, "matched": len(jobs)})
        except Exception as e:  # noqa: BLE001
            status.append({"company": "(Jobindex RSS)", "source": "jobindex", "ok": False, "error": str(e)[:300]})

    # --- dedup: samme virksomhed + samme titel = samme job (virksomhedens egen kilde vinder over Jobindex)
    by_key: dict[str, dict] = {}
    for j in found:
        d = j.to_dict()
        key = f"{d['company']}|{norm_title(d['title'])}"
        if key in by_key:
            prev = by_key[key]
            if prev["source"] == "jobindex" and d["source"] != "jobindex":
                d["also_on"] = sorted(set(prev.get("also_on", []) + ["jobindex"]))
                by_key[key] = d
            else:
                prev["also_on"] = sorted(set(prev.get("also_on", []) + [d["source"]]))
            continue
        by_key[key] = d

    current = {}
    for d in by_key.values():
        if not d["deadline"]:
            d["deadline"] = find_deadline(d["description_md"], today.year) or ""
        d["tags"] = topic_tags(d["title"], d["description_md"])
        prev = old.get(d["id"])
        d["first_seen"] = prev["first_seen"] if prev else now
        d["last_seen"] = now
        d["active"] = not (d["deadline"] and d["deadline"] < today.isoformat())
        current[d["id"]] = d

    # jobs vi ikke så i dag: behold, men marker inaktive hvis kilden faktisk virkede
    for jid, prev in old.items():
        if jid in current:
            continue
        if prev["company"] in ok_companies and prev["source"] != "jobindex":
            prev["active"] = False
        elif prev.get("deadline") and prev["deadline"] < today.isoformat():
            prev["active"] = False
        current[jid] = prev

    jobs_out = sorted(current.values(), key=lambda j: (not j["active"], j["first_seen"]), reverse=False)
    jobs_out.sort(key=lambda j: (j["active"], j["first_seen"]), reverse=True)
    new = [j for j in jobs_out if j["first_seen"] == now and j["active"]]

    (DATA / "jobs.json").write_text(json.dumps({"updated": now, "count": len(jobs_out), "jobs": jobs_out}, ensure_ascii=False, indent=1))
    (DATA / "new.json").write_text(json.dumps({"updated": now, "count": len(new), "jobs": new}, ensure_ascii=False, indent=1))
    (DATA / "status.json").write_text(json.dumps({"updated": now, "companies": status}, ensure_ascii=False, indent=1))
    export_tracker(jobs_out, status, companies, now)
    print(f"\nFærdig: {len(found)} fundet i dag, {len(new)} nye, {sum(j['active'] for j in jobs_out)} aktive i alt.")


def export_tracker(jobs_out, status, companies, now):
    """Færdige tracker-dokumenter (ren data) til den planlagte Claude-opgave, så den ikke skal køre kode fra repoet."""
    ranks = {c["name"]: c.get("rank") for c in companies}
    tdir = DATA / "tracker"
    docs = tdir / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    for f in docs.glob("*.json"):
        f.unlink()
    index = []
    for j in jobs_out:
        if not j.get("active", True):
            index.append({"id": j["id"], "active": False, "deadline": j.get("deadline", "")})
            continue
        doc = {k: j.get(k) for k in ("title", "company", "location", "url", "apply_url", "deadline", "posted",
                                      "description_md", "source", "tags", "first_seen", "last_seen", "active")}
        doc["rank"] = ranks.get(j["company"])
        (docs / f"{j['id']}.json").write_text(json.dumps(doc, ensure_ascii=False))
        index.append({"id": j["id"], "active": True, "company": j["company"], "title": j["title"],
                      "location": j.get("location", ""), "deadline": j.get("deadline", ""), "tags": j.get("tags", []),
                      "excerpt": (j.get("description_md") or "")[:1500]})
    direct = [c for c in status if c.get("source") not in ("jobindex", "none")]
    run = {"updated": now, "active_count": sum(1 for j in jobs_out if j.get("active", True)),
           "sources_ok": sum(1 for c in direct if c.get("ok")), "sources_total": len(companies),
           "jobindex_ok": any(c.get("ok") for c in status if c.get("source") == "jobindex")}
    (tdir / "index.json").write_text(json.dumps({"updated": now, "run": run, "jobs": index}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

"""Forbereder synkronisering fra data/jobs.json til Studiejob Radar-trackeren (artifact-databasen).

Trin 1 (uden --scores):
    python tools/sync_prepare.py --db-dump DIR --out OUT
    -> OUT/to_score.json : nye job, der skal have en AI-score (kort uddrag af hvert opslag)
Trin 2 (med --scores):
    python tools/sync_prepare.py --db-dump DIR --out OUT --scores OUT/scores.json
    -> OUT/docs/<id>.json    : fulde dokumenter til nye job   (op=set)
    -> OUT/updates/<id>.json : små ændringer til eksisterende (op=update)
    -> OUT/plan.json         : batches (max 50) klar til ArtifactData batch med file_path
    -> OUT/run.json          : dokumentet meta/run

DIR er mappen fra ArtifactData list(collection="jobs", out_dir=DIR); filer DIR/jobs/<id>.json.
scores.json: {"<id>": {"score": 0-100, "reason": "én sætning"}, ...}
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def load_db(dump: Path) -> dict:
    out = {}
    for f in (dump / "jobs").glob("*.json") if dump and (dump / "jobs").exists() else []:
        raw = json.loads(f.read_text())
        doc = raw.get("data", raw) if isinstance(raw, dict) else {}
        out[f.stem] = {"doc": doc, "version": raw.get("version")}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-dump", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--scores", type=Path)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)

    data = json.loads((ROOT / "data" / "jobs.json").read_text())
    status = json.loads((ROOT / "data" / "status.json").read_text()) if (ROOT / "data" / "status.json").exists() else {}
    ranks = {c["name"]: c["rank"] for c in yaml.safe_load((ROOT / "companies.yaml").read_text())["companies"]}
    db = load_db(a.db_dump) if a.db_dump else {}

    new = [j for j in data["jobs"] if j["id"] not in db and j.get("active", True)]
    unscored = [k for k, v in db.items() if v["doc"].get("score") is None]

    if not a.scores:
        items = [{"id": j["id"], "company": j["company"], "title": j["title"], "location": j.get("location", ""),
                  "tags": j.get("tags", []), "deadline": j.get("deadline", ""),
                  "excerpt": (j.get("description_md") or "")[:1800]} for j in new]
        for k in unscored:
            d = db[k]["doc"]
            items.append({"id": k, "company": d.get("company"), "title": d.get("title"), "location": d.get("location", ""),
                          "tags": d.get("tags", []), "excerpt": (d.get("description_md") or "")[:1800]})
        (a.out / "to_score.json").write_text(json.dumps(items, ensure_ascii=False, indent=1))
        print(f"{len(items)} job skal scores ({len(new)} nye, {len(unscored)} uden score). Fil: {a.out/'to_score.json'}")
        return

    scores = json.loads(a.scores.read_text())
    (a.out / "docs").mkdir(exist_ok=True)
    (a.out / "updates").mkdir(exist_ok=True)
    entries = []
    for j in new:
        s = scores.get(j["id"], {})
        doc = {k: j.get(k) for k in ("title", "company", "location", "url", "apply_url", "deadline", "posted",
                                      "description_md", "source", "tags", "first_seen", "last_seen", "active")}
        doc.update(rank=ranks.get(j["company"]), score=s.get("score"), reason=s.get("reason", ""), status="ny")
        (a.out / "docs" / f"{j['id']}.json").write_text(json.dumps(doc, ensure_ascii=False))
        entries.append({"op": "set", "collection": "jobs", "doc_id": j["id"], "file_path": str((a.out / "docs" / f"{j['id']}.json").resolve())})

    by_id = {j["id"]: j for j in data["jobs"]}
    for k, v in db.items():
        d, patch = v["doc"], {}
        j = by_id.get(k)
        if j:
            for f in ("active", "deadline", "last_seen", "apply_url", "tags"):
                if j.get(f) != d.get(f):
                    patch[f] = j.get(f)
            if d.get("rank") is None and ranks.get(j["company"]):
                patch["rank"] = ranks[j["company"]]
        if k in scores and d.get("score") is None:
            patch.update(score=scores[k].get("score"), reason=scores[k].get("reason", ""))
        if patch:
            (a.out / "updates" / f"{k}.json").write_text(json.dumps(patch, ensure_ascii=False))
            e = {"op": "update", "collection": "jobs", "doc_id": k, "file_path": str((a.out / "updates" / f"{k}.json").resolve())}
            if v.get("version"):
                e["if_version"] = v["version"]
            entries.append(e)

    batches = [entries[i:i + 50] for i in range(0, len(entries), 50)]
    (a.out / "plan.json").write_text(json.dumps(batches, ensure_ascii=False, indent=1))

    comps = status.get("companies", [])
    active = sum(1 for j in data["jobs"] if j.get("active", True))
    run = {"updated": data.get("updated") or datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "synced": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "new_count": len(new), "active_count": active,
           "sources_ok": sum(1 for c in comps if c.get("ok") and c.get("source") != "jobindex"),
           "sources_total": sum(1 for c in comps if c.get("source") != "jobindex"),
           "jobindex_ok": any(c.get("ok") for c in comps if c.get("source") == "jobindex"),
           "top_new": sorted(({"title": j["title"], "company": j["company"], "score": scores.get(j["id"], {}).get("score")} for j in new),
                             key=lambda x: -(x["score"] or 0))[:5]}
    (a.out / "run.json").write_text(json.dumps(run, ensure_ascii=False))
    print(f"{len(new)} nye, {len(entries) - len(new)} opdateringer, {len(batches)} batch(es). Plan: {a.out/'plan.json'}")


if __name__ == "__main__":
    main()

"""Eksport til Jobradar-appen (Lovable/Supabase).

Appen henter data/platform/jobs.json fra GitHub (raw-URL) og upserter i databasen.
Skemaet er en kontrakt: ændr det kun ved at hæve SCHEMA_VERSION og opdatere appens sync-funktion.

    python -m scraper.export        # genbyg eksporten ud fra data/jobs.json + data/status.json
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "platform"
SCHEMA_VERSION = 1
MAX_DESC = 20000

FIELDS = ("id", "company", "title", "url", "apply_url", "location", "deadline", "posted", "first_seen",
          "last_seen", "active", "source", "fit", "tags", "top50", "description_md")


def to_platform_job(j: dict, ranks: dict) -> dict:
    out = {k: j.get(k) for k in FIELDS}
    out["deadline"] = (j.get("deadline") or None)
    out["posted"] = (j.get("posted") or None)
    out["fit"] = j.get("fit") or "sikker"
    out["tags"] = j.get("tags") or []
    out["top50"] = bool(j.get("top50", True))
    out["rank"] = ranks.get(j.get("company")) if out["top50"] else None
    out["origin"] = "jobindex" if j.get("source") == "jobindex" else "employer"
    out["also_on"] = j.get("also_on") or []
    out["description_md"] = (j.get("description_md") or "")[:MAX_DESC]
    out["active"] = bool(j.get("active", True))
    return out


REQUIRED = {"id": str, "company": str, "title": str, "url": str, "active": bool, "origin": str, "fit": str,
            "tags": list, "top50": bool, "description_md": str}
DATE_FIELDS = ("deadline", "posted")


def validate_payload(payload: dict) -> list[str]:
    """Kontrakttjek af eksporten. Returnerer en liste af fejl (tom = gyldig)."""
    import re
    errs = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errs.append("forkert schema_version")
    ids = set()
    for i, j in enumerate(payload.get("jobs", [])):
        where = f"job[{i}] {j.get('id')}"
        for k, t in REQUIRED.items():
            if not isinstance(j.get(k), t):
                errs.append(f"{where}: {k} skal være {t.__name__}")
        if not j.get("title", "").strip() or not str(j.get("url", "")).startswith("http"):
            errs.append(f"{where}: mangler titel eller gyldig url")
        for k in DATE_FIELDS:
            if j.get(k) is not None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(j[k])):
                errs.append(f"{where}: {k}={j[k]!r} er ikke en dato")
        if j.get("fit") not in ("sikker", "sandsynlig", "mulig"):
            errs.append(f"{where}: ukendt fit {j.get('fit')!r}")
        if j.get("id") in ids:
            errs.append(f"{where}: dubleret id")
        ids.add(j.get("id"))
    return errs[:50]


def export_platform(jobs_out: list[dict], status: list[dict], companies: list[dict], now: str) -> dict:
    ranks = {c["name"]: c.get("rank") for c in companies}
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = [to_platform_job(j, ranks) for j in jobs_out]
    sources = [{"name": s.get("company"), "type": s.get("source"), "ok": s.get("ok"), "listed": s.get("listed"),
                "matched": s.get("matched"), "error": (s.get("error") or "")[:200] or None} for s in status]
    payload = {"schema_version": SCHEMA_VERSION, "generated_at": now,
               "counts": {"total": len(jobs), "active": sum(j["active"] for j in jobs)},
               "jobs": jobs}
    errs = validate_payload(payload)
    if errs:
        (OUT / "jobs.invalid.json").write_text(json.dumps({"errors": errs, **payload}, ensure_ascii=False))
        raise ValueError("Platform-eksporten er ugyldig og blev IKKE skrevet: " + "; ".join(errs[:5]))
    (OUT / "jobs.json").write_text(json.dumps(payload, ensure_ascii=False))
    (OUT / "sources.json").write_text(json.dumps({"generated_at": now, "sources": sources}, ensure_ascii=False, indent=1))
    return payload


def main():
    import yaml
    jobs = json.loads((DATA / "jobs.json").read_text())
    status = json.loads((DATA / "status.json").read_text())
    companies = yaml.safe_load((ROOT / "companies.yaml").read_text())["companies"]
    p = export_platform(jobs["jobs"], status["companies"], companies, jobs["updated"])
    print("platform-eksport:", p["counts"])


if __name__ == "__main__":
    main()

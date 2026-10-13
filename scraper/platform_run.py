"""Jobradar-kørslen (platformen). Adskilt fra den personlige kørsel i scraper/run.py.

Forskelle fra den personlige kørsel:
  - arbejdsgivere fra platform/employers.yaml (ikke companies.yaml)
  - INGEN Jobindex – kun arbejdsgivernes egne systemer
  - jobtyper: studiejob, praktik og graduate (job_type)
  - geografi: Sjælland inkl. Storkøbenhavn (region)
  - nøgleord fra platform/keywords.yaml (dansk + engelsk) i stedet for de personlige emner
Output i data/jobradar/: jobs.json (kontrakt til appen, schema_version 2), keywords.json, study_lines.json,
employers.json, status.json (til sundhedstjekket) og state.json (historik).

    python -m scraper.platform_run
    python -m scraper.platform_run --only "Tryg"
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import traceback
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

from .adapters import ADAPTERS
from .common import find_deadline, job_type, region, set_job_types, set_topics
from .run import SOURCE_TIMEOUT, _with_timeout, norm_title, suspicious

ROOT = Path(__file__).resolve().parent.parent
PLAT = ROOT / "platform"
OUT = ROOT / "data" / "jobradar"
SCHEMA_VERSION = 2
JOB_TYPES = {"studiejob", "praktik", "graduate"}
# Søgeord til adaptere, der søger (Workday, SuccessFactors, Oracle …). Bredere end den personlige kørsel.
PLATFORM_TERMS = ["student", "studentermedhjælper", "student assistant", "studiejob", "part-time",
                  "intern", "internship", "praktik", "praktikant", "graduate", "trainee"]
TERM_TYPES = {"workday", "successfactors", "phenom", "nordea", "oracle", "browser"}
PRUNE_DAYS = 30
MAX_DESC = 20000


def load_keywords() -> list[dict]:
    return yaml.safe_load((PLAT / "keywords.yaml").read_text())["keywords"]


def load_study_lines() -> list[dict]:
    return yaml.safe_load((PLAT / "study_lines.yaml").read_text())["study_lines"]


def load_employers() -> list[dict]:
    """Håndplukkede (employers.yaml) + automatisk opdagede (discovered.yaml). Navne er unikke; håndplukkede vinder."""
    emps = yaml.safe_load((PLAT / "employers.yaml").read_text())["employers"]
    disc_f = PLAT / "discovered.yaml"
    if disc_f.exists():
        names = {e["name"].lower() for e in emps}
        for e in yaml.safe_load(disc_f.read_text()).get("employers") or []:
            if e["name"].lower() not in names:
                emps.append(e)
                names.add(e["name"].lower())
    return emps


def compile_keywords(kws: list[dict]) -> dict[str, re.Pattern]:
    return {k["id"]: re.compile(k["pattern"], re.I) for k in kws}


def match_keywords(rx: dict[str, re.Pattern], title: str, text: str, company: str = "") -> list[str]:
    """Nøgleord i titel + tekst (dansk og engelsk).
    - Virksomhedens navn fjernes først (ellers får alle Danske Bank-job 'bank').
    - Et ord tæller, hvis det står i titlen, mindst 2 gange i teksten, eller i den første del af teksten (hvor selve
      jobbet beskrives). Så fanger vi ikke standardfraser som "vi tilbyder pension" én gang nederst i opslaget."""
    def strip(s: str) -> str:
        for part in {company, *company.split()}:
            if len(part) >= 4:
                s = re.sub(re.escape(part), " ", s, flags=re.I)
        return s
    t, body = strip(title), strip(text[:15000])
    cut = len(body) if len(body) < 400 else int(len(body) * 0.6)

    def hit(r: re.Pattern) -> bool:
        if r.search(t):
            return True
        found = list(r.finditer(body))
        return len(found) >= 2 or (bool(found) and found[0].start() < cut)
    return [k for k, r in rx.items() if hit(r)]


def build_record(job: dict, employer: dict, rx: dict, now: str) -> dict | None:
    """Job fra en adapter → platform-job, eller None hvis det ikke hører til i Jobradar."""
    jt = job_type(job["title"], job.get("description_md", ""))
    if not jt:
        return None
    reg = region(job.get("location"), job["title"])
    if reg is None:
        return None
    desc = job.get("description_md") or ""
    # "mulig" = deltid uden tegn på studier. Kun med, hvis titlen selv rammer et fagligt nøgleord
    # (ellers kommer fx "Laboratory Technician" og "Tutti violinist" med som studiejob).
    if jt == "studiejob" and job.get("fit") == "mulig" and not any(r.search(job["title"]) for r in rx.values()):
        return None
    deadline = job.get("deadline") or find_deadline(desc, date.today().year) or None
    apply_url = job.get("apply_url") or job.get("url")
    return {
        "id": job["id"], "company": job["company"], "title": job["title"], "url": job.get("url") or apply_url, "job_type": jt, "fit": job.get("fit") or "sikker",
        "location": job.get("location") or "", "region": reg,
        "posted": (job.get("posted") or "")[:10] or None, "deadline": deadline,
        "apply_url": apply_url, "career_url": employer.get("career_url") or None,
        "apply_is_direct": bool(apply_url),
        "keywords": match_keywords(rx, job["title"], desc, job["company"]),
        "lines": [],   # 13/10: arbejdsgivere mærkes ikke længere med studieretninger
        "source": job.get("source"),
        "description_md": desc[:MAX_DESC],
    }


REQUIRED = {"id": str, "company": str, "title": str, "job_type": str, "region": str, "keywords": list, "lines": list,
            "active": bool, "first_seen": str, "description_md": str}


def validate(payload: dict, keyword_ids: set[str]) -> list[str]:
    errs = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errs.append("forkert schema_version")
    ids = set()
    for i, j in enumerate(payload.get("jobs", [])):
        w = f"job[{i}] {j.get('id')}"
        for k, t in REQUIRED.items():
            if not isinstance(j.get(k), t):
                errs.append(f"{w}: {k} skal være {t.__name__}")
        if j.get("job_type") not in JOB_TYPES:
            errs.append(f"{w}: ukendt job_type {j.get('job_type')!r}")
        if j.get("region") not in ("storkbh", "sjaelland", "ukendt"):
            errs.append(f"{w}: ukendt region {j.get('region')!r}")
        if not (str(j.get("apply_url") or "").startswith("http") or str(j.get("career_url") or "").startswith("http")):
            errs.append(f"{w}: hverken apply_url eller career_url")
        for k in ("posted", "deadline"):
            if j.get(k) is not None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(j[k])):
                errs.append(f"{w}: {k}={j[k]!r} er ikke en dato")
        unknown = set(j.get("keywords", [])) - keyword_ids
        if unknown:
            errs.append(f"{w}: ukendte nøgleord {sorted(unknown)}")
        det = j.get("details")
        if det is not None and not (isinstance(det, dict) and isinstance(det.get("summary", ""), str)
                                    and all(isinstance(det.get(k, []), list) for k in ("tasks", "requirements", "offer", "contacts"))):
            errs.append(f"{w}: details har forkert form")
        if j.get("source") == "jobindex":
            errs.append(f"{w}: Jobindex må ikke være kilde i Jobradar")
        if j.get("id") in ids:
            errs.append(f"{w}: dubleret id")
        ids.add(j.get("id"))
    return errs[:50]


def merge_state(found: dict[str, dict], old: dict[str, dict], ok_sources: set[str], now: str, today: str) -> dict[str, dict]:
    """Sætter first_seen/last_seen/active. Job fra en kilde, der virkede, men som ikke længere findes → inaktiv."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=PRUNE_DAYS)).isoformat(timespec="seconds")
    out = {}
    for jid, j in found.items():
        prev = old.get(jid)
        j["first_seen"] = prev["first_seen"] if prev else now
        j["last_seen"] = now
        j["active"] = not (j.get("deadline") and j["deadline"] < today)
        out[jid] = j
    for jid, prev in old.items():
        if jid in out:
            continue
        if prev["company"] in ok_sources or (prev.get("deadline") and prev["deadline"] < today):
            prev["active"] = False
        if not prev.get("active") and prev.get("last_seen", now) < cutoff:
            continue
        out[jid] = prev
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", action="append")
    args = ap.parse_args(argv)

    kws = load_keywords()
    rx = compile_keywords(kws)
    set_job_types(JOB_TYPES)
    set_topics({k["id"]: k["pattern"] for k in kws})   # adapternes emne-krav bruger nu den brede ordbog
    employers = load_employers()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    today = date.today().isoformat()
    OUT.mkdir(parents=True, exist_ok=True)

    state_f = OUT / "state.json"
    state = json.loads(state_f.read_text()) if state_f.exists() else {"jobs": {}, "sources": {}}
    prev_status = {s["company"]: s for s in state.get("sources", {}).values()}

    found, status, ok_sources = {}, [], set()
    by_key = {}
    for e in employers:
        if args.only and e["name"] not in args.only:
            continue
        src = dict(e.get("source") or {})
        typ = src.get("type", "none")
        entry = {"company": e["name"], "source": typ, "lines": e.get("lines", [])}
        if typ not in ADAPTERS or typ == "jobindex":
            entry.update(ok=None, note=e.get("note") or e.get("status"))
            status.append(entry)
            continue
        cfg = {**src, "name": e["name"]}
        if typ in TERM_TYPES and "search_terms" not in cfg:
            cfg["search_terms"] = PLATFORM_TERMS
        t0 = time.time()
        try:
            listed, jobs = _with_timeout(lambda: ADAPTERS[typ](cfg), SOURCE_TIMEOUT)
            kept = 0
            for j in jobs:
                rec = build_record(j.to_dict(), e, rx, now)
                if not rec:
                    continue
                key = f"{rec['company']}|{norm_title(rec['title'])}"
                if key in by_key:
                    continue
                by_key[key] = rec["id"]
                found[rec["id"]] = rec
                kept += 1
            entry.update(ok=True, listed=listed, matched=kept)
            prev = prev_status.get(e["name"], {})
            sus = suspicious(listed, prev.get("listed") or prev.get("last_good_listed"))
            if sus:
                entry["suspect"] = sus
                entry["last_good_listed"] = prev.get("listed") or prev.get("last_good_listed")
            else:
                ok_sources.add(e["name"])
        except Exception as ex:  # noqa: BLE001
            entry.update(ok=False, error=f"{type(ex).__name__}: {str(ex)[:300]}")
            pv = prev_status.get(e["name"], {})
            entry["last_good_listed"] = pv.get("listed") or pv.get("last_good_listed")
            traceback.print_exc(file=sys.stderr)
        entry["seconds"] = round(time.time() - t0, 1)
        print(f"{e['name']:<36} {typ:<15} {entry.get('ok')} {entry.get('listed', '')} {entry.get('matched', '')} "
              f"{entry.get('suspect') or entry.get('error') or ''}")
        status.append(entry)

    if not args.only and state["jobs"] and not found:
        print("STOP: ingen job fundet – beholder forrige data.", file=sys.stderr)
        sys.exit(2)

    jobs = merge_state(found, state["jobs"], ok_sources, now, today)
    for j in jobs.values():                       # ældre tilstand uden url-felt (før 13/10)
        j.setdefault("url", j.get("apply_url") or j.get("career_url"))
    ordered = sorted(jobs.values(), key=lambda j: (j["active"], j["first_seen"]), reverse=True)
    from .enrich import enrich_jobs
    print("AI-strukturering:", enrich_jobs(ordered))
    for j in ordered:                             # frist fra AI, hvis kilden ikke havde en
        dl = (j.get("details") or {}).get("deadline", "")
        if not j.get("deadline") and re.fullmatch(r"\d{4}-\d{2}-\d{2}", dl or ""):
            j["deadline"] = dl
            j["active"] = dl >= today
    payload = {"schema_version": SCHEMA_VERSION, "generated_at": now,
               "counts": {"total": len(ordered), "active": sum(j["active"] for j in ordered)}, "jobs": ordered}
    errs = validate(payload, set(rx))
    if errs:
        (OUT / "jobs.invalid.json").write_text(json.dumps({"errors": errs}, ensure_ascii=False, indent=1))
        raise SystemExit("Eksporten er ugyldig og blev IKKE skrevet: " + "; ".join(errs[:5]))

    merged_sources = {**state.get("sources", {}), **{s["company"]: s for s in status}}
    (OUT / "jobs.json").write_text(json.dumps(payload, ensure_ascii=False))
    (OUT / "state.json").write_text(json.dumps({"jobs": jobs, "sources": merged_sources}, ensure_ascii=False))
    (OUT / "status.json").write_text(json.dumps({"updated": now, "companies": status}, ensure_ascii=False, indent=1))
    (OUT / "keywords.json").write_text(json.dumps(
        {"keywords": [{k: v for k, v in kw.items() if k != "pattern"} for kw in kws]}, ensure_ascii=False, indent=1))
    (OUT / "study_lines.json").write_text(json.dumps({"study_lines": load_study_lines()}, ensure_ascii=False, indent=1))
    (OUT / "employers.json").write_text(json.dumps({"employers": [
        {"name": e["name"], "lines": [], "status": e.get("status"), "career_url": e.get("career_url"),
         "source_type": (e.get("source") or {}).get("type", "none"),
         **{k: merged_sources.get(e["name"], {}).get(k) for k in ("ok", "listed", "matched")}} for e in employers]},
        ensure_ascii=False, indent=1))
    by_type = {}
    for j in ordered:
        if j["active"]:
            by_type[j["job_type"]] = by_type.get(j["job_type"], 0) + 1
    print(f"\nFærdig: {len(found)} fundet i dag, {payload['counts']['active']} aktive. Pr. type: {by_type}")


if __name__ == "__main__":
    main()

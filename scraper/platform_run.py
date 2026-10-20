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
from urllib.parse import urlparse

import yaml

from .adapters import ADAPTERS
from .common import REJECTED, find_deadline, job_type, region, reject, set_job_types, set_topics
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
    """Håndplukkede (employers.yaml) + automatisk opdagede (discovered.yaml). Navne er unikke; håndplukkede vinder.
    Arbejdsgivere i blocked.yaml (fx rekrutteringsbureauer) springes altid over."""
    emps = yaml.safe_load((PLAT / "employers.yaml").read_text())["employers"]
    blocked_f = PLAT / "blocked.yaml"
    blocked = {b["name"].lower() for b in (yaml.safe_load(blocked_f.read_text()) or {}).get("blocked") or []} \
        if blocked_f.exists() else set()
    emps = [e for e in emps if e["name"].lower() not in blocked]
    disc_f = PLAT / "discovered.yaml"
    if disc_f.exists():
        from .discover_jobindex import known_keys
        names = {e["name"].lower() for e in emps}
        for e in yaml.safe_load(disc_f.read_text()).get("employers") or []:
            if known_keys([e]) & known_keys(emps):
                continue                  # samme kilde som en håndplukket arbejdsgiver
            if e["name"].lower() not in names and e["name"].lower() not in blocked:
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



# Hosts, der tilhører et rekrutteringssystem og ikke arbejdsgiveren (giver forkert logo).
ATS_HOSTS = ("hr-manager.net", "oraclecloud.com", "myworkdayjobs.com", "csod.com", "emply.com", "elvium.com",
             "successfactors.com", "successfactors.eu", "teamtailor.com", "smartrecruiters.com", "yello.co",
             "eightfold.ai", "phenompeople.com", "amazon.jobs", "jobindex.dk")


def company_domain(employer: dict) -> str | None:
    """Arbejdsgiverens eget domæne (til logo i appen): `domain` i yaml, ellers udledt af karrieresiden."""
    if employer.get("domain"):
        return employer["domain"]
    host = urlparse(employer.get("career_url") or "").netloc.lower().split(":")[0]
    if not host or any(host == h or host.endswith("." + h) for h in ATS_HOSTS):
        return None
    labels = host.split(".")
    return ".".join(labels[-2:]) if len(labels) >= 2 else None


def build_record(job: dict, employer: dict, rx: dict, now: str) -> dict | None:
    """Job fra en adapter → platform-job, eller None hvis det ikke hører til i Jobradar."""
    jt = job_type(job["title"], job.get("description_md", ""))
    if not jt:
        return None
    reg = region(job.get("location"), job["title"])
    if reg is None:
        return None
    if reg == "ukendt" and employer.get("region") in ("storkbh", "sjaelland"):
        reg = employer["region"]          # fx Emply/Yello, der kun skriver "Danmark"
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


def why_rejected(job: dict, rx: dict) -> str:
    """Kort årsag til, at build_record sagde nej (til rejected.json)."""
    if not job_type(job["title"], job.get("description_md", "")):
        return "ikke studiejob/praktik/graduate"
    if region(job.get("location"), job["title"]) is None:
        return f"uden for Sjælland ({(job.get('location') or '')[:40]})"
    return "deltid uden fagligt nøgleord i titlen"


def write_rejected(path: Path, rejected: list[dict]) -> None:
    """data/jobradar/rejected.json: pr. arbejdsgiver antal frasorterede opslag pr. årsag + op til 40 eksempler.
    Bruges til at finde filtre, der er for stramme, og kilder, der ser opslag men aldrig giver job."""
    by: dict[str, dict] = {}
    for r in rejected:
        c = by.setdefault(r["company"], {"count": 0, "reasons": {}, "examples": []})
        c["count"] += 1
        c["reasons"][r["reason"].split(" (")[0]] = c["reasons"].get(r["reason"].split(" (")[0], 0) + 1
        if len(c["examples"]) < 40:
            c["examples"].append({k: r[k] for k in ("title", "reason", "url") if r.get(k)})
    path.write_text(json.dumps({"companies": dict(sorted(by.items()))}, ensure_ascii=False, indent=1))


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
        source = prev.get("source_employer") or prev["company"]   # fælles portaler: kilden ≠ firmanavnet
        if source in ok_sources or (prev.get("deadline") and prev["deadline"] < today):
            prev["active"] = False
        if not prev.get("active") and prev.get("last_seen", now) < cutoff:
            continue
        out[jid] = prev
    return out


READ_DAYS = 30          # en kilde "læses", hvis den har givet opslag inden for så mange dage


def data_since(entry: dict, prev: dict, now: str) -> str | None:
    """Hvornår kilden sidst gav opslag (listed > 0). Gemmes i state.json som `last_data`.
    Ældre tilstand uden feltet: har kilden tidligere givet opslag, regnes det som nu (engangs-overgang 20/10)."""
    if entry.get("ok") and (entry.get("listed") or 0) > 0:
        return now
    if prev.get("last_data"):
        return prev["last_data"]
    if any((d.get(k) or 0) > 0 for d in (prev, entry) for k in ("listed", "last_good_listed")):
        return now
    return None


def is_read(src: dict | None, now: str) -> bool:
    """Læses kilden faktisk? Kun hvis den har givet opslag inden for READ_DAYS. En kilde, der er sat op, men aldrig har
    givet data (forkert adresse, bot-mur, nyt system), står som "læses ikke endnu" – også selv om status er "klar"."""
    last = (src or {}).get("last_data")
    if not last:
        return False
    try:
        age = datetime.fromisoformat(now) - datetime.fromisoformat(last)
    except ValueError:
        return False
    return age <= timedelta(days=READ_DAYS)


def employer_list(employers: list[dict], jobs: list[dict], sources: dict, now: str | None = None) -> list[dict]:
    """Arbejdsgiverlisten til appen (/arbejdsgivere).

    Fælles portaler (fx Statens Rekrutteringsløsning) giver job med den rigtige arbejdsgivers navn. Portalen selv vises
    ikke; i stedet får hver arbejdsgiver med aktive job fra portalen sin egen række (status klar, portalens kilde), så
    tallene i appen passer med jobbene.

    `reading` ("læses" | "læses-ikke-endnu") fortæller appen, om arbejdsgiveren reelt bliver læst automatisk (se
    is_read). `last_data` er datoen, kilden sidst gav opslag."""
    now = now or datetime.now(timezone.utc).isoformat(timespec="seconds")
    known = {n.lower() for e in employers for n in [e["name"], *(e.get("aliases") or [])]}
    portals, subs = set(), {}
    for j in jobs:
        src = j.get("source_employer")
        if src and src != j["company"]:
            portals.add(src)
            if j.get("active") and j["company"].lower() not in known:
                subs.setdefault(j["company"], {"via": src, "domain": j.get("company_domain"), "career_url": j.get("career_url")})
    by_name = {e["name"]: e for e in employers}
    via_portal: dict[str, tuple[str, int]] = {}      # arbejdsgiver uden egen kilde, men med aktive job fra en portal
    for j in jobs:
        src = j.get("source_employer")
        if j.get("active") and src and src != j["company"]:
            n = j["company"].lower()
            via_portal[n] = (src, via_portal.get(n, (src, 0))[1] + 1)
    portal_names = portals | {e["name"] for e in employers if (e.get("source") or {}).get("multi_employer")}
    portal_read = next((p for p in sorted(portal_names) if is_read(sources.get(p), now)), None)

    def read_fields(src_name: str | None, read: bool) -> dict:
        last = (sources.get(src_name) or {}).get("last_data") if src_name else None
        return {"reading": "læses" if read else "læses-ikke-endnu", "last_data": (last or "")[:10] or None}

    out = []
    for e in employers:
        if e["name"] in portals and (e.get("source") or {}).get("type") != "none":
            continue
        if e.get("region") == "udenfor":
            continue                                  # springes over i kørslen, så de skal heller ikke vises i appen
        row = {"name": e["name"], "lines": [], "status": e.get("status"), "career_url": e.get("career_url"),
               "domain": company_domain(e), "source_type": (e.get("source") or {}).get("type", "none"),
               **{k: sources.get(e["name"], {}).get(k) for k in ("ok", "listed", "matched")}}
        row.update(read_fields(e["name"], row["source_type"] != "none" and is_read(sources.get(e["name"]), now)))
        if row["source_type"] == "none":
            hit = next((via_portal[n.lower()] for n in [e["name"], *(e.get("aliases") or [])] if n.lower() in via_portal), None)
            if hit:
                portal = by_name.get(hit[0], {})
                row.update(status="klar", via=hit[0], ok=True, matched=hit[1],
                           source_type=(portal.get("source") or {}).get("type", "none"),
                           **read_fields(hit[0], is_read(sources.get(hit[0]), now)))   # bevarede job beviser intet
            elif e.get("status") == "via-portal" and portal_read:
                row.update(via=portal_read, **read_fields(portal_read, True))   # portalen læses; ingen job lige nu
        out.append(row)
    for name, sub in sorted(subs.items()):
        portal = by_name.get(sub["via"], {})
        out.append({"name": name, "lines": [], "status": "klar", "career_url": sub["career_url"] or portal.get("career_url"),
                    "domain": sub["domain"], "source_type": (portal.get("source") or {}).get("type", "none"),
                    "via": sub["via"], "ok": True, **read_fields(sub["via"], is_read(sources.get(sub["via"]), now))})
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
    REJECTED.clear()

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
        if e.get("region") == "udenfor":
            typ = "none"                  # arbejdsgiveren ligger uden for Sjælland – gamle job lukkes
            ok_sources.add(e["name"])
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
                    reject(e["name"], j.title, why_rejected(j.to_dict(), rx), j.url)
                    continue
                rec["source_employer"] = e["name"]   # hvilken kilde jobbet kom fra (appen bruger ikke feltet)
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
        entry["last_data"] = data_since(entry, prev_status.get(e["name"], {}), now)
        entry["seconds"] = round(time.time() - t0, 1)
        print(f"{e['name']:<36} {typ:<15} {entry.get('ok')} {entry.get('listed', '')} {entry.get('matched', '')} "
              f"{entry.get('suspect') or entry.get('error') or ''}")
        status.append(entry)

    if not args.only and state["jobs"] and not found:
        print("STOP: ingen job fundet – beholder forrige data.", file=sys.stderr)
        sys.exit(2)

    if not args.only:                             # job fra arbejdsgivere, der ikke længere er med (fx dubletter)
        current = {e["name"] for e in employers}
        for j in state["jobs"].values():
            if (j.get("source_employer") or j["company"]) not in current:
                j["active"] = False
    jobs = merge_state(found, state["jobs"], ok_sources, now, today)
    for j in jobs.values():                       # ældre tilstand uden url-felt (før 13/10)
        j.setdefault("url", j.get("apply_url") or j.get("career_url"))
    domains = {}
    for e in employers:                           # også aliaser, så job fra fælles portaler får logo (fx "Banedanmark")
        for n in [e["name"], *(e.get("aliases") or [])]:
            domains.setdefault(n, company_domain(e))
    for j in jobs.values():                       # logo-domæne (13/10) – også for ældre job i tilstanden
        j["company_domain"] = domains.get(j["company"]) or j.get("company_domain")
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
    write_rejected(OUT / "rejected.json", REJECTED)
    (OUT / "status.json").write_text(json.dumps({"updated": now, "companies": status}, ensure_ascii=False, indent=1))
    (OUT / "keywords.json").write_text(json.dumps(
        {"keywords": [{k: v for k, v in kw.items() if k != "pattern"} for kw in kws]}, ensure_ascii=False, indent=1))
    (OUT / "study_lines.json").write_text(json.dumps({"study_lines": load_study_lines()}, ensure_ascii=False, indent=1))
    (OUT / "employers.json").write_text(json.dumps({"employers": employer_list(employers, ordered, merged_sources, now)},
                                                   ensure_ascii=False, indent=1))
    by_type = {}
    for j in ordered:
        if j["active"]:
            by_type[j["job_type"]] = by_type.get(j["job_type"], 0) + 1
    print(f"\nFærdig: {len(found)} fundet i dag, {payload['counts']['active']} aktive. Pr. type: {by_type}")


if __name__ == "__main__":
    main()

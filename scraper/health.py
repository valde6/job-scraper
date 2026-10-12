"""Sundhedstjek efter hver kørsel: opdager kilder, der er gået i stykker, før brugerne gør.

Læser data/status.json og data/platform/jobs.json, fører historik i data/health/history.jsonl og skriver
  data/health/latest.json   maskinlæsbar status pr. kilde
  data/health/report.md     menneskelæsbar rapport
  data/health/alert.md      findes KUN når der er noget, et menneske skal kigge på (bruges til GitHub-issue)

    python -m scraper.health
"""
from __future__ import annotations

import json
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
HDIR = DATA / "health"
KEEP = 240          # ca. 30 dage ved kørsel hver 3. time
ALERT_AFTER = 2     # en kilde skal fejle i 2 kørsler i træk, før vi slår alarm (enkeltfejl er ofte midlertidige)


def classify(entry: dict, history: list[dict]) -> str | None:
    """Returnerer problemtype for én kilde eller None. history = tidligere entries for samme kilde (nyeste sidst)."""
    if entry.get("ok") is None:
        return None                                    # ingen direkte kilde
    if entry.get("ok") is False:
        return "fejl"
    if entry.get("suspect"):
        return "mistænkelig"
    listed = entry.get("listed") or 0
    prev = [h.get("listed") for h in history[-5:] if h.get("ok") and h.get("listed")]
    if prev:
        m = median(prev)
        if listed == 0:
            return "tom"
        if m >= 10 and listed < 0.3 * m:
            return "fald"
    return None


def streak(problem_now: str | None, history: list[dict]) -> int:
    """Hvor mange kørsler i træk kilden har haft et problem (inkl. nu)."""
    if not problem_now:
        return 0
    n = 1
    for h in reversed(history):
        if h.get("problem"):
            n += 1
        else:
            break
    return n


def evaluate(status: list[dict], history_rows: list[dict], active_now: int) -> dict:
    by_src: dict[str, list[dict]] = {}
    for row in history_rows:
        for s in row.get("sources", []):
            by_src.setdefault(s["name"], []).append(s)
    sources, alerts = [], []
    for e in status:
        name = e.get("company")
        hist = by_src.get(name, [])
        prob = classify(e, hist)
        st = streak(prob, hist)
        sources.append({"name": name, "type": e.get("source"), "ok": e.get("ok"), "listed": e.get("listed"),
                        "matched": e.get("matched"), "problem": prob, "streak": st,
                        "detail": e.get("error") or e.get("suspect")})
        if prob and st >= ALERT_AFTER:
            alerts.append(f"**{name}** ({e.get('source')}): {prob} i {st} kørsler i træk"
                          + (f" – {(e.get('error') or e.get('suspect'))[:200]}" if (e.get('error') or e.get('suspect')) else ""))
    prev_active = [r.get("active") for r in history_rows[-5:] if r.get("active")]
    if prev_active and active_now < 0.6 * median(prev_active):
        alerts.append(f"**Samlet:** kun {active_now} aktive job mod normalt ca. {int(median(prev_active))}")
    return {"sources": sources, "alerts": alerts, "active": active_now}


def main(argv=None):
    """Standard: den personlige kørsel (data/). Med --dir data/jobradar: platform-kørslen."""
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=None, help="datamappe for platform-kørslen, fx data/jobradar")
    args = ap.parse_args(argv)
    if args.dir:
        base = ROOT / args.dir
        status_file, plat, hdir = base / "status.json", base / "jobs.json", base / "health"
    else:
        status_file, plat, hdir = DATA / "status.json", DATA / "platform" / "jobs.json", HDIR
    run(status_file, plat, hdir)


def run(status_file: Path, plat: Path, HDIR: Path):
    HDIR.mkdir(parents=True, exist_ok=True)
    status = json.loads(status_file.read_text())
    active = json.loads(plat.read_text())["counts"]["active"] if plat.exists() else 0
    hfile = HDIR / "history.jsonl"
    rows = [json.loads(l) for l in hfile.read_text().splitlines() if l.strip()] if hfile.exists() else []
    res = evaluate(status["companies"], rows, active)

    rows.append({"ts": status["updated"], "active": active,
                 "sources": [{k: s[k] for k in ("name", "ok", "listed", "problem")} for s in res["sources"]]})
    hfile.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows[-KEEP:]) + "\n")
    (HDIR / "latest.json").write_text(json.dumps({"ts": status["updated"], **res}, ensure_ascii=False, indent=1))

    probs = [s for s in res["sources"] if s["problem"]]
    lines = [f"# Scraper-sundhed {status['updated']}", "",
             f"Aktive job: {active}. Kilder med problemer: {len(probs)}.", ""]
    if probs:
        lines += ["| Kilde | Type | Problem | I træk | Detalje |", "|---|---|---|---|---|"]
        lines += [f"| {s['name']} | {s['type']} | {s['problem']} | {s['streak']} | {(s['detail'] or '')[:120]} |" for s in probs]
    (HDIR / "report.md").write_text("\n".join(lines) + "\n")

    # Til GitHub-issuet: kommentér kun når sættet af alarmer ændrer sig (ellers spam hver 3. time)
    prev_key = ""
    if (HDIR / "alert_key.txt").exists():
        prev_key = (HDIR / "alert_key.txt").read_text().strip()
    key = "|".join(sorted(a.split("**")[1] for a in res["alerts"] if "**" in a))
    (HDIR / "alert_key.txt").write_text(key + "\n")
    changed = HDIR / "alert_changed"
    if key and key != prev_key:
        changed.write_text(key)
    elif changed.exists():
        changed.unlink()

    alert = HDIR / "alert.md"
    if res["alerts"]:
        alert.write_text("Scraperen har kilder, der ser ud til at være gået i stykker:\n\n"
                         + "\n".join(f"- {a}" for a in res["alerts"])
                         + f"\n\nSe `{HDIR.relative_to(ROOT)}/report.md`. Tip: giv dette issue til en kode-agent (se AGENTS.md).\n")
    elif alert.exists():
        alert.unlink()
    print("\n".join(lines))
    print("ALARM:" if res["alerts"] else "Ingen alarmer.", *res["alerts"], sep="\n")


if __name__ == "__main__":
    main()

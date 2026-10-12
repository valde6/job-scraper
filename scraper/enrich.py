"""AI-strukturering af jobopslag til Studieradar.

Hvert job sendes ÉN gang gennem Claude Haiku, som udtrækker:
  summary, tasks (arbejdsopgaver), requirements (hvad de forventer), about (om arbejdspladsen),
  practical (timer, start, sted), contacts (navn, titel, telefon, e-mail) og sprog.
Resultatet caches i data/jobradar/enriched/<id>.json sammen med en hash af opslagsteksten, så et job kun
genbehandles, hvis teksten ændrer sig. Uden ANTHROPIC_API_KEY springes trinnet over (appen viser så kun fakta + link).

    ANTHROPIC_API_KEY=... python -m scraper.enrich          # behandler aktive job uden struktur
Køres automatisk fra platform_run (workflow jobradar-scrape), hvor nøglen ligger som GitHub-secret.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "jobradar" / "enriched"
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-5-5")
PROMPT_VERSION = 1
MAX_PER_RUN = int(os.environ.get("ENRICH_MAX_PER_RUN", "150"))
MAX_INPUT_CHARS = 14000

SYSTEM = (
    "Du strukturerer jobopslag for en jobportal til studerende. Du får titel, virksomhed og opslagets tekst "
    "(kan indeholde menutekst og støj fra hjemmesiden – ignorér den). Udfyld værktøjet save_job. Regler: "
    "Skriv på SAMME sprog som opslaget. Brug kun information, der står i opslaget – gæt aldrig. "
    "Korte, konkrete punkter (maks 12 ord hver, maks 7 punkter pr. liste). Omskriv med egne ord frem for at kopiere hele sætninger. "
    "Kontaktpersoner: kun personer, opslaget selv angiver som kontakt for spørgsmål til stillingen. Udelad felter, der ikke står i opslaget."
)

TOOL = {
    "name": "save_job",
    "description": "Gem den strukturerede version af jobopslaget.",
    "input_schema": {
        "type": "object",
        "properties": {
            "language": {"type": "string", "enum": ["da", "en", "other"], "description": "Opslagets sprog"},
            "summary": {"type": "string", "description": "1-2 sætninger: hvad jobbet går ud på"},
            "tasks": {"type": "array", "items": {"type": "string"}, "description": "Arbejdsopgaver"},
            "requirements": {"type": "array", "items": {"type": "string"}, "description": "Hvad de forventer af dig (uddannelse, kompetencer, erfaring)"},
            "about": {"type": "string", "description": "Om arbejdspladsen/teamet, maks 3 sætninger"},
            "offer": {"type": "array", "items": {"type": "string"}, "description": "Hvad de tilbyder (løn, fleksibilitet, udvikling) – kun hvis nævnt"},
            "hours_per_week": {"type": "string", "description": "Fx '15-20 timer', kun hvis nævnt"},
            "start": {"type": "string", "description": "Startdato/-tidspunkt, kun hvis nævnt"},
            "location": {"type": "string", "description": "Arbejdssted (by/adresse), kun hvis nævnt"},
            "deadline": {"type": "string", "description": "Ansøgningsfrist som YYYY-MM-DD, kun hvis nævnt"},
            "contacts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}, "title": {"type": "string"},
                                   "phone": {"type": "string"}, "email": {"type": "string"}},
                    "required": ["name"],
                },
            },
        },
        "required": ["language", "summary", "tasks", "requirements"],
    },
}


def text_hash(job: dict) -> str:
    raw = f"{PROMPT_VERSION}|{job.get('title')}|{job.get('description_md') or ''}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def load_cached(job_id: str) -> dict | None:
    f = CACHE / f"{job_id}.json"
    return json.loads(f.read_text()) if f.exists() else None


def call_claude(job: dict, api_key: str) -> dict:
    user = (f"Titel: {job.get('title')}\nVirksomhed: {job.get('company')}\nSted (fra kilden): {job.get('location')}\n\n"
            f"Opslagets tekst:\n{(job.get('description_md') or '')[:MAX_INPUT_CHARS]}")
    body = {"model": MODEL, "max_tokens": 1500, "system": SYSTEM, "tools": [TOOL],
            "tool_choice": {"type": "tool", "name": "save_job"},
            "messages": [{"role": "user", "content": user}]}
    for attempt in range(3):
        r = requests.post("https://api.anthropic.com/v1/messages", json=body, timeout=60,
                          headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        if r.status_code in (429, 500, 502, 503, 529) and attempt < 2:
            time.sleep(5 * (attempt + 1))
            continue
        r.raise_for_status()
        for block in r.json().get("content", []):
            if block.get("type") == "tool_use" and block.get("name") == "save_job":
                return clean_details(block["input"])
        raise ValueError("Intet save_job-svar fra modellen")
    raise RuntimeError("Gav op efter 3 forsøg")


def clean_details(d: dict) -> dict:
    """Normalisér modellens svar: trim, fjern tomme felter, begræns længder."""
    out = {}
    for k in ("language", "summary", "about", "hours_per_week", "start", "location", "deadline"):
        v = (d.get(k) or "").strip() if isinstance(d.get(k), str) else ""
        if v:
            out[k] = v[:600]
    for k in ("tasks", "requirements", "offer"):
        items = [str(x).strip()[:200] for x in (d.get(k) or []) if str(x).strip()]
        if items:
            out[k] = items[:7]
    contacts = []
    for c in d.get("contacts") or []:
        if isinstance(c, dict) and (c.get("name") or "").strip():
            contacts.append({k: str(c[k]).strip()[:120] for k in ("name", "title", "phone", "email") if c.get(k)})
    if contacts:
        out["contacts"] = contacts[:3]
    if out.get("language") not in ("da", "en", "other"):
        out["language"] = "other"
    return out


def enrich_jobs(jobs: list[dict], api_key: str | None = None, caller=call_claude) -> dict:
    """Tilføjer job['details'] fra cache eller AI. Returnerer statistik."""
    api_key = api_key if api_key is not None else os.environ.get("ANTHROPIC_API_KEY", "")
    CACHE.mkdir(parents=True, exist_ok=True)
    stats = {"cached": 0, "new": 0, "failed": 0, "skipped_no_key": 0, "over_limit": 0}
    budget = MAX_PER_RUN
    for j in jobs:
        if not j.get("active"):
            continue
        h = text_hash(j)
        cached = load_cached(j["id"])
        if cached and cached.get("hash") == h:
            j["details"] = cached["details"]
            stats["cached"] += 1
            continue
        if not api_key:
            if cached:
                j["details"] = cached["details"]          # gammel struktur er bedre end ingen
            stats["skipped_no_key"] += 1
            continue
        if budget <= 0:
            stats["over_limit"] += 1
            continue
        budget -= 1
        try:
            details = caller(j, api_key)
            (CACHE / f"{j['id']}.json").write_text(json.dumps(
                {"hash": h, "model": MODEL, "prompt_version": PROMPT_VERSION, "details": details}, ensure_ascii=False, indent=1))
            j["details"] = details
            stats["new"] += 1
        except Exception as e:  # noqa: BLE001
            stats["failed"] += 1
            print(f"enrich fejl {j['id']} {j.get('title', '')[:40]}: {type(e).__name__}: {str(e)[:150]}")
    return stats


def main():
    f = ROOT / "data" / "jobradar" / "jobs.json"
    payload = json.loads(f.read_text())
    stats = enrich_jobs(payload["jobs"])
    f.write_text(json.dumps(payload, ensure_ascii=False))
    print("enrich:", stats)


if __name__ == "__main__":
    main()

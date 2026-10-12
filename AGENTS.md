# AGENTS.md – instruktioner til kode-agenter (Claude Code, Codex m.fl.)

Læs hele filen, før du ændrer noget. Den er kort med vilje.

## Hvad projektet er
Scraperen bag **Jobradar** (studiejob-app til studerende i Danmark). Den henter studiejob direkte fra
arbejdsgivernes rekrutteringssystemer (Workday, SuccessFactors, HR-Manager, Teamtailor m.fl.) og fra
Jobindex' RSS, og udgiver dem som `data/platform/jobs.json`. Appen (Lovable + Supabase, separat repo)
henter filen hver time. **Scraperens kvalitet er hele produktets værdi** – hellere færre job end forkerte job.

## To kørsler i samme repo
| | Personlig (Valdemars tracker) | Jobradar (platformen) |
|---|---|---|
| Kode | `scraper/run.py` | `scraper/platform_run.py` |
| Arbejdsgivere | `companies.yaml` | `platform/employers.yaml` |
| Filtre | studiejob, Storkøbenhavn, personlige emner | studiejob + praktik + graduate, Sjælland, `platform/keywords.yaml` (DA/EN) |
| Jobindex | ja (kun personlig brug) | **aldrig** |
| Output | `data/jobs.json`, `data/tracker/`, `data/platform/` | `data/jobradar/` (kontrakt v2, se `docs/STUDIERADAR-APP.md`) |
| Workflow | `scrape-jobs` | `jobradar-scrape` |

Adapterne er fælles. Platform-tilstanden slås til med `set_job_types()` og `set_topics()` i `common.py`.

## Kort over koden
| Fil | Ansvar |
|---|---|
| `companies.yaml` | Arbejdsgivere og deres kilde (`source.type` vælger adapter) |
| `scraper/adapters/<type>.py` | Én adapter pr. rekrutteringssystem. Signatur: `scrape(cfg) -> (antal_set, [Job])` |
| `scraper/common.py` | HTTP (med optag/afspil), tekst → markdown, filtre: `student_fit`, `topic_tags`, `is_cph`, `find_deadline` |
| `scraper/run.py` | Kører alle kilder, dedup, aktiv/inaktiv-logik, vagter mod ødelagte kilder, skriver `data/` |
| `scraper/export.py` | **Kontrakten** til appen (`SCHEMA_VERSION`, `validate_payload`) |
| `scraper/health.py` | Sundhedstjek efter hver kørsel → `data/health/` + GitHub-issue med label `scraper-health` |
| `scraper/record.py` | Optager rigtige HTTP-svar til `tests/fixtures/<virksomhed>/` |
| `scraper/probe.py` | Fejlfinding via GitHub Actions (skriv linjer i `probe.txt` og push) |
| `tests/` | pytest. `test_adapters_replay.py` afspiller fixtures uden netværk |

## Kommandoer
```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q                              # skal være grønt før du er færdig
python -m scraper.run --only "LEGO Group"        # kør én kilde mod de rigtige sider
python -m scraper.record --only "LEGO Group"     # optag nye fixtures efter en tilsigtet ændring
python -m scraper.export                         # genbyg + validér app-eksporten
python -m scraper.health                         # sundhedsrapport
```
Kan du ikke nå job-siderne fra dit miljø (fx cloud-sandkasse med blokeret netværk), så brug GitHub Actions:
`probe.txt` (GET/POST/GREP/BROWSER/SCRAPE/PYMOD-linjer) eller `triggers/record` → push → læs resultatet i `data/probe/`.

## Regler
1. **Ingen hemmeligheder i repoet.** Aldrig tokens, nøgler eller adgangskoder i kode, commits eller logs.
2. **Kør `python -m pytest -q` før du afleverer.** Rød test = ikke færdig.
3. **Ændr ikke eksportens felter** uden at hæve `SCHEMA_VERSION` og skrive det i din opsummering – appen afhænger af dem.
4. **Én adapter pr. system, ikke pr. virksomhed.** Ny arbejdsgiver på et kendt system = kun en linje i `companies.yaml`.
5. **Foretræk officielle JSON-API'er/feeds** frem for HTML, og HTML frem for browser (Playwright). Browser er sidste udvej.
6. **Respektér robots.txt** og hold lav frekvens. Ingen omgåelse af bot-mure, CAPTCHA eller login.
7. **Filtrene i `common.py` er produktets definition af et studiejob.** Ændrer du dem, så tilføj/ret tests i `tests/test_common.py`, der viser hvorfor.
8. Små, fokuserede ændringer. Én opgave pr. branch/PR. Skriv commit-beskeder på dansk.

## Opskrifter
**Tilføj en arbejdsgiver:** find systemet (`python -m scraper.discover --only "<navn>"` eller se linket i et opslag) →
tilføj i `companies.yaml` → `python -m scraper.run --only "<navn>"` → `python -m scraper.record --only "<navn>"` → tests.

**Ret en kilde der er gået i stykker** (issue med label `scraper-health`):
1. Reproducér: `python -m scraper.run --only "<navn>"` (eller probe via Actions).
2. Find årsagen: ny URL, ændret JSON-felt, bot-mur? Kig på det rå svar, gæt ikke.
3. Ret adapteren eller konfigurationen, optag nye fixtures, kør tests.
4. Kan den ikke rettes lovligt (bot-mur), så sæt `source.type: none` med en `note`, så den dækkes via Jobindex.

**Ny adapter:** kopiér den mest lignende adapter, behold signaturen, brug `get/post` fra `common.py`
(så optag/afspil virker), sæt `fit=student_fit(...)`, registrér i `scraper/adapters/__init__.py`, optag fixtures.

## Definition of done
- `python -m pytest -q` er grønt
- Nye/ændrede adaptere har fixtures i `tests/fixtures/`
- `data/platform/jobs.json` validerer (`python -m scraper.export`)
- Kort opsummering: hvad blev ændret, hvorfor, og hvad er ikke testet

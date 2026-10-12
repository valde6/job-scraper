# job-scraper

Scraperen bag **Jobradar**. Udgiver `data/platform/jobs.json`, som appen henter hver time.
Agenter: læs `AGENTS.md`. Opgaver: `docs/BACKLOG.md`. Læring: `docs/AGENT-GUIDE.md`.

Personlig scraper, der henter **studenterjob i Danmark** fra karrieresiderne hos 50 top-arbejdsgivere
(Universum-rankingen) og fra Jobindex' RSS-feed.

- Kører automatisk hver 3. time via GitHub Actions (`.github/workflows/scrape.yml`), med sundhedstjek og automatisk issue, når en kilde går i stykker
- Tests: `python -m pytest -q` (kører også i CI på hver push/PR)
- Resultater i `data/`:
  - `jobs.json` – alle job (aktive + udløbne) med fuld opslagstekst i markdown, ansøgningslink og frist
  - `new.json` – job fundet for første gang i seneste kørsel
  - `status.json` – hvilke kilder virkede, og hvor mange opslag hver gav
- Claude (Cowork) læser `new.json`, giver hvert job en relevansscore og lægger dem i job-trackeren.

## Tilføj eller ret en virksomhed
Redigér `companies.yaml`. `source.type` vælger adapteren (se `scraper/adapters/`).

## Kør lokalt
```bash
pip install -r requirements.txt
python -m scraper.run                  # alle
python -m scraper.run --only "LEGO Group"
python -m scraper.discover --only "Nordea"   # find hvilket rekrutteringssystem en virksomhed bruger
```

Kun til personlig brug. Scraperen respekterer robots.txt for Jobindex og henter kun offentlige opslag.

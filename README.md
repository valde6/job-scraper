# job-scraper

Personlig scraper, der henter **studenterjob i Danmark** fra karrieresiderne hos 50 top-arbejdsgivere
(Universum-rankingen) og fra Jobindex' RSS-feed.

- Kører automatisk man–fre ca. kl. 06:15 via GitHub Actions (`.github/workflows/scrape.yml`)
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

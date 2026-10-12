---
description: Tilføj en ny arbejdsgiver som direkte kilde
argument-hint: <virksomhedsnavn>
---
Tilføj "$ARGUMENTS" som direkte kilde.

1. Find arbejdsgiverens karriereside og rekrutteringssystem (`python -m scraper.discover`, eller åbn et aktuelt opslag og se hvor "Søg"-knappen fører hen).
2. Bruger de et system, vi har en adapter til, så er opgaven kun en ny blok i `companies.yaml`. Ellers: stop og beskriv systemet og en plan for en ny adapter – byg den ikke uden at spørge.
3. `python -m scraper.run --only "$ARGUMENTS"` skal give `ok` og mindst ét opslag set.
4. Optag fixtures og kør `python -m pytest -q`.

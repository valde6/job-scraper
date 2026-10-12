---
description: Ret en kilde der er gået i stykker (fx fra et scraper-health issue)
argument-hint: <virksomhedsnavn som i companies.yaml>
---
Kilden "$ARGUMENTS" er gået i stykker eller giver mistænkelige resultater.

1. Læs AGENTS.md og den aktuelle sundhedsrapport i `data/health/report.md` og `data/status.json` for "$ARGUMENTS".
2. Reproducér med `python -m scraper.run --only "$ARGUMENTS"`. Kan du ikke nå siden, så lav en probe (se AGENTS.md).
3. Find den præcise årsag ud fra det rå svar. Skriv årsagen i én sætning, før du ændrer kode.
4. Lav den mindste ændring, der løser det. Optag nye fixtures (`python -m scraper.record --only "$ARGUMENTS"`).
5. Kør `python -m pytest -q`. Aflevér en kort opsummering: årsag, ændring, hvad der ikke er testet.

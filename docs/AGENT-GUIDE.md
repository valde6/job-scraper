# Kode med agenter – guide til Jobradar

Målet er at du lærer at styre kode-agenter (Claude Code og Codex) på et rigtigt projekt. Øvelserne bygger
videre på hinanden og løser samtidig rigtige opgaver fra `docs/BACKLOG.md`.

## De fem principper
1. **Agenten er kun så god som dens feedback-loop.** Den kan selv køre `pytest`, så den kan selv se, om den har ret. Derfor har repoet tests og optagede HTTP-svar.
2. **Kontekst slår prompt.** `AGENTS.md` (Codex) og `CLAUDE.md` (Claude Code) læses automatisk. Skriv regler dér én gang i stedet for i hver prompt.
3. **Små opgaver med et klart "færdig".** "Byg Emply-adapteren, færdig når tests er grønne" virker. "Gør scraperen bedre" gør ikke.
4. **Plan før kode.** Lad agenten foreslå en plan, ret den, og lad den så kode. Det er billigere at rette en plan end en diff.
5. **Du er reviewer.** Læs altid diffen. Spørg agenten "hvad er ikke testet?" – den ved det tit godt selv.

## Opsætning (én gang)
```bash
git clone https://github.com/valde6/job-scraper.git && cd job-scraper
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q                                      # skal være grønt
```
Installer begge agenter: Claude Code (`claude` i terminalen) og Codex CLI (`codex`). Start dem fra repo-mappen.
Fordel lokalt: din computer kan nå job-siderne direkte, så agenten kan køre `python -m scraper.run --only ...` selv.

---

## Øvelse 1 – Første opgave med plan mode (Claude Code, ca. 30 min)
Opgave: **Backlog 5 (rens opslagstekst)** – lille, afgrænset og testbar.
1. Start `claude`. Tryk Shift+Tab, til der står *plan mode*.
2. Skriv: `/backlog 5`
3. Læs planen. Ret den, hvis den vil ændre mere end nødvendigt ("rør kun common.py, browser-adapteren og tests").
4. Godkend. Se agenten skrive tests, køre dem og rette.
5. `git diff` – læs hver linje. Commit selv.

**Det lærer du:** plan mode, projekt-kommandoer, at tests styrer agenten.

## Øvelse 2 – Samme slags opgave i Codex (ca. 30 min)
Opgave: **Backlog 6 (Jobindex i afspilningstests)**.
1. Start `codex` i repoet. Den læser `AGENTS.md` automatisk.
2. Skriv: "Løs opgave 6 i docs/BACKLOG.md. Vis mig en plan først."
3. Sammenlign med Claude Code: Hvordan planlægger de? Hvor tit spørger de? Hvem kører flest tests?

**Det lærer du:** at forskellige agenter har forskellige styrker, og at `AGENTS.md` gør dem udskiftelige.

## Øvelse 3 – En rigtig feature (Claude Code, 1-2 timer)
Opgave: **Backlog 1 (Emply-adapter)**. Her skal agenten undersøge et ukendt API.
1. Plan mode: "Undersøg først, hvordan Emply-listen hentes. Lav ingen kode, før du har vist mig et rigtigt svar fra API'et."
2. Når formatet er fundet: lad den bygge adapteren efter opskriften i `AGENTS.md`.
3. Bed den til sidst om at optage fixtures og køre hele test-suiten.

**Det lærer du:** at lade agenten undersøge før den bygger, og at stoppe den, når den gætter.

## Øvelse 4 – To agenter parallelt (ca. 1 time)
Agenter kan arbejde samtidig, hvis de ikke deler mappe. Brug git worktrees:
```bash
git worktree add ../js-dtu -b dtu-kilde
git worktree add ../js-discovery -b auto-discovery
```
- Terminal 1: `cd ../js-dtu && claude` → `/backlog 2`
- Terminal 2: `cd ../js-discovery && codex` → "Løs opgave 3 i docs/BACKLOG.md"

Push begge branches og åbn pull requests på GitHub. CI (`tests`-workflowet) kører automatisk på hver PR.
Merge den ene, og lad den anden agent løse eventuelle konflikter: "Rebase på main og løs konflikterne".

**Det lærer du:** parallelle agenter, branches/PR'er og CI som fælles kvalitetskontrol.

## Øvelse 5 – Agenten som vagthund (ca. 30 min)
Når en kilde går i stykker, opretter scraperen automatisk et GitHub-issue med label `scraper-health`.
1. Åbn issuet, og kopiér navnet på kilden.
2. I Claude Code: `/fix-source <navn>`
3. Lad agenten åbne en PR, der lukker issuet ("Fixes #12" i beskrivelsen).

**Det lærer du:** at koble automatiske alarmer til agenter – det er sådan, scraperen bliver "bulletproof" over tid.

## Øvelse 6 – Hooks: automatisk kvalitet (ca. 20 min)
Lad Claude Code køre tests automatisk efter hver ændring af en Python-fil. Bed Claude Code om:
"Tilføj et PostToolUse-hook i .claude/settings.json, der kører `python -m pytest -q -x` efter Edit/Write på .py-filer."
Læs bagefter `.claude/settings.json` og forstå, hvad den lavede.

**Det lærer du:** at gøre regler til automatik i stedet for noget, agenten skal huske.

## Øvelse 7 – Appen (efter GitHub er forbundet i Lovable)
Klon Jobradar-repoet og lav en `AGENTS.md` dér også (bed agenten skrive den ud fra koden).
Tag så **Backlog 8 (AI-match-score)** med Claude Code. Lovable henter ændringerne fra GitHub automatisk,
så du bruger ikke Lovable-credits på det.

**Det lærer du:** at arbejde med agenter på tværs af to repoer, og at holde Lovable til det visuelle.

---

## Gode prompts at stjæle
- "Vis mig en plan først. Ingen kode før jeg siger go."
- "Hvad er den mindste ændring, der løser det?"
- "Kør testene og vis mig outputtet – ikke en opsummering."
- "Hvad har du antaget, som du ikke har verificeret?"
- "Stop. Du gætter. Hent det rigtige svar fra siden først."

## Faldgruber
- **Lange sessioner bliver dumme.** Start en ny session pr. opgave (`/clear` i Claude Code).
- **Agenten "fikser" testen i stedet for koden.** Kig efter ændringer i `tests/` – var de tilsigtede?
- **Hemmeligheder.** Indsæt aldrig tokens i chatten med en agent. Brug miljøvariabler/secrets.

# Backlog

Opgaver i agent-størrelse: hver kan løses i én session/PR og har et klart "færdig"-kriterium.
Tag dem med `/backlog <nr>` i Claude Code eller ved at give Codex teksten. Afkryds med en kort note, når de er merged.

**To kørsler i samme repo:**
- *Personlig* (`scraper/run.py`, `companies.yaml`, workflow `scrape-jobs`) – Valdemars egen tracker. Rør kun ved den, hvis opgaven siger det.
- *Jobradar* (`scraper/platform_run.py`, `platform/*.yaml`, workflow `jobradar-scrape`) – platformen. Ingen Jobindex.
Begge bruger de samme adaptere. Testene beskytter begge.

## Jobradar-scraperen (prioriteret)

- [ ] **1. Emply-adapter.** Emply bruges af kommuner, a-kasser og foreninger (Ældre Sagen, AKA, Frederiksberg Kommune m.fl.).
  Listesiden `https://<kunde>.career.emply.com/ledige-stillinger` henter opslag via `/api/integration/vacancy/get-page`.
  Find request-formatet (din browsers netværksfane), byg `scraper/adapters/emply.py` (config: `url`), sæt `status: klar` for Emply-arbejdsgiverne i
  `platform/employers.yaml`. Færdig: `python -m scraper.platform_run --only "Ældre Sagen"` giver opslag, fixtures optaget, tests grønne.
- [ ] **2. Udfyld rekrutteringssystemer fra discovery.** Workflowet `discover-ats` med `PLATFORM` i `triggers/discover` skriver
  `data/jobradar/discovery.json` for alle arbejdsgivere med `status: find-system`. Gå listen igennem, tilføj `source` til dem med et kendt system,
  og test hver med `platform_run --only`. Færdig: mindst 30 flere arbejdsgivere med `status: klar`.
- [ ] **3. HR-Manager-aliaser.** Københavns Kommune (cid 1518), ITU (119), HOFOR (174), Lederne (2134) bruger HR-Manager, men adapteren skal bruge
  kunde-aliaset. Find det i et opslag (`customer=` i HTML'en, se `probe.txt` GREP) og tilføj. Færdig: fire nye kilder virker.
- [ ] **4. Statens Rekrutteringsløsning.** Kunden `statensrekrutteringsloesning_tr` viste 25 stillinger og ingen studiejob, selvom 8 studiejob fra
  samme løsning lå på Jobindex. Find ud af, hvor de publiceres (andre aliaser? `MediaId`?). Færdig: forklaring + evt. flere kilder.
- [ ] **5. Rens opslagstekst.** Browser-kilder (fx PFA) får menutekst med i `description_md` ("Gå til hovedindhold", "Log på" …).
  `clean_description()` i `common.py` med tests, brugt i browser-adapteren.
- [ ] **6. Jobindex som intern pejling.** Scriptet læser Jobindex-opslag, følger linket til arbejdsgiverens system og skriver *kandidater* til
  `data/jobradar/discovered_sources.json` (navn, system, config). **Intet indhold fra Jobindex gemmes eller vises.** Ingen automatisk ændring af
  `employers.yaml`. Grundlag: `scraper/experiments/apply_study.py`. Færdig: filen opdateres ugentligt, tests for genkendelsen.
- [ ] **7. Cornerstone-adapter** (Egmont/Nordisk Film, NNE: `*.csod.com`). Færdig: Nordisk Film som kilde.
- [ ] **8. Jobnet-webservice.** Når STAR har givet adgang: adapter, der henter studiejob i Region Hovedstaden/Sjælland fra Jobnet. Dækker de små arbejdsgivere.
- [ ] **9. Praktik/graduate-kvalitet.** Gennemgå 50 tilfældige job fra `data/jobradar/jobs.json`: er `job_type`, `region` og `keywords` rigtige?
  Ret regex i `common.py`/`platform/keywords.yaml` med en test pr. fejl.
- [ ] **10. Afspilningstests for platform-kørslen.** Optag fixtures med platform-søgeordene (`scraper/record.py --platform`), så `platform_run` kan testes uden netværk.

## Den personlige scraper

- [ ] **11. Jobindex i afspilningstests.** Optag et lille sæt RSS-feeds + opslag og test parseren (virksomhed fra titel/logo, top50-flag, praktik-afvisning).

## Appen (Studieradar – det repo, Lovable er forbundet til)
Specifikation og opgave 0-8 står i [`docs/STUDIERADAR-APP.md`](STUDIERADAR-APP.md). Opgave 0 kopierer filen ind i app-repoet som `docs/STUDIERADAR-SPEC.md`.

## Senere (efter scraper, UI og backend er på plads)
- **AI-match-score** (0-100 + én sætning om hvorfor) pr. bruger og job, ud fra profil, nøgleord og fravalg. Erstatter `hits` i `src/lib/match.ts`.
- **AI-resumé pr. job** (3 linjer: opgaver, krav, timer) – vises i stedet for opslagsteksten.
- **AI-hjælp til ansøgning** (udkast ud fra profil + opslag).

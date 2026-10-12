# Backlog

Opgaver i agent-størrelse: hver kan løses i én session/PR og har et klart "færdig"-kriterium.
Tag dem med `/backlog <nr>` i Claude Code eller ved at give Codex teksten. Afkryds med en kort note, når de er merged.

## Scraper

- [ ] **1. Emply-adapter.** Emply bruges af kommuner, a-kasser og foreninger (Ældre Sagen, KP, AKA, Hedensted Kommune m.fl.).
  Listesiden `https://<kunde>.career.emply.com/ledige-stillinger` henter opslag via `/api/integration/vacancy/get-page`.
  Find request-formatet (browserens netværksfane eller `BROWSER`-probe), byg `scraper/adapters/emply.py` (config: `tenant`),
  tilføj 2 kunder i `companies.yaml`. Færdig: `run --only` giver opslag, fixtures optaget, tests grønne.
- [ ] **2. DTU som kilde.** DTU bruger Oracle (`https://efzu.fa.em2.oraclecloud.com`, site `CX_1`) – adapteren findes.
  Beslut først, hvordan arbejdsgivere uden for top 50 markeres (`top50: false`-felt i `companies.yaml`?). Færdig: DTU-studiejob i eksporten med `top50=false`.
- [ ] **3. Automatisk kilde-opdagelse.** For hvert Jobindex-opslag: følg linket i opslaget, genkend systemet
  (HR-Manager `cid=`, Emply `<kunde>.career.emply.com`, Teamtailor, Workday `<kunde>.wdN.myworkdayjobs.com/<site>`, Oracle-host + site)
  og skriv kandidater til `data/discovered_sources.json` (navn, type, config, antal set). Ingen automatisk ændring af `companies.yaml`.
  Grundlag: `scraper/experiments/apply_study.py`. Færdig: filen opdateres i hver kørsel, tests for genkendelsen.
- [ ] **4. Statens Rekrutteringsløsning.** HR-Manager-kunden `statensrekrutteringsloesning_tr` (cid 3010) viste 25 stillinger og ingen
  studiejob, selvom Jobindex havde 8 studiejob fra samme cid. Find ud af, hvor de publiceres (andre kunde-aliaser? `MediaId`?).
  Færdig: en forklaring + evt. kilde i `companies.yaml`.
- [ ] **5. Rens opslagstekst.** Browser-kilder (fx PFA) får menutekst med i `description_md` ("Gå til hovedindhold", "Log på" …).
  Lav en `clean_description()` i `common.py` med tests, og brug den i browser-adapteren.
- [ ] **6. Jobindex i afspilningstests.** Optag et lille sæt RSS-feeds + opslag og test parseren (virksomhedsnavn fra titel/logo, `top50`-flag, afvisning af praktik).
- [ ] **7. Kildestatus i eksporten.** Tilføj `data/platform/sources.json` til appens `/status`-side (kræver ændring i app-repoet).

## App (Jobradar – Lovable-repoet)

- [ ] **8. AI-match-score.** Edge function, der for hver bruger scorer nye job 0-100 ud fra profil + `excluded_fields`
  (fx "Revision" → under 50) og skriver `user_jobs.score` + `score_reason`. Billig model, batch, kun nye job. Kræver en API-nøgle som secret i Lovable Cloud.
- [ ] **9. AI-resumé pr. job.** Én gang pr. job: 3 linjer "hvad laver man", "krav", "timer". Vises i stedet for de første 800 tegn.
- [ ] **10. E-mail med nye match** (ugentlig), når score ≥ 70.

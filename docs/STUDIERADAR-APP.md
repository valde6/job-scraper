# Studieradar – specifikation for app-repoet

Appen hedder **Studieradar** (domæne: studieradar.live). Den er bygget i Lovable, og koden ligger i det GitHub-repo,
Lovable er forbundet til. Denne fil kopieres ind i app-repoet som `docs/STUDIERADAR-SPEC.md` (se opgave 0).

Læs også app-repoets egen `AGENTS.md`: typer i `src/lib/types.ts`, dataadgang i `src/hooks/`, synkronisering i
`src/lib/sync.server.ts` og server-route `src/routes/api/public/sync-jobs.ts`.

## Arbejdsregler for kode-agenten
1. Tag én opgave ad gangen (nederst i filen). Vis en plan, før du skriver kode.
2. Kør `bun install` (første gang), derefter `bun run test` og `bun run build`. Begge skal lykkes.
3. **Commit lokalt** med en kort dansk commit-besked. **Push ikke** – Valdemar pusher selv via GitHub Desktop.
   (Alt, der pushes til main, synkroniseres til Lovable og bliver live.)
4. **Rør ikke databasens skema.** Lovable Cloud-databasen kan ikke ændres fra GitHub. Skemaet er allerede klar (afsnit 2).
   Har en opgave brug for en ny kolonne/tabel, så skriv SQL'en i `docs/sql/<dato>-<navn>.sql` og stop – Valdemar får den kørt.
5. `src/integrations/supabase/types.ts` er genereret af Lovable og kender ikke de nye kolonner endnu. Opdatér den i hånden,
   så den matcher afsnit 2 (Row/Insert/Update for hver tabel).
6. Alt UI-tekst er dansk. Appen må aldrig nævne eller linke til Jobindex.

## Princip: overblik på 3 sekunder
Studerende gider ikke læse lange opslag. Hvert job skal kunne vurderes med det samme:
**hvad, hvem, hvor, hvornår – og en knap til arbejdsgiverens egen ansøgning.**

## 1. Datafeed fra scraperen
Scraperen (`valde6/job-scraper`, offentligt repo) udgiver hver 3. time:

| URL | Indhold |
|---|---|
| `https://raw.githubusercontent.com/valde6/job-scraper/main/data/jobradar/jobs.json` | `{schema_version: 2, generated_at, counts, jobs[]}` |
| `https://raw.githubusercontent.com/valde6/job-scraper/main/data/jobradar/keywords.json` | `{keywords: [{id, label, en, group}]}` |
| `https://raw.githubusercontent.com/valde6/job-scraper/main/data/jobradar/study_lines.json` | `{study_lines: [{id, name, school, description, suggested[], avoid[]}]}` |
| `https://raw.githubusercontent.com/valde6/job-scraper/main/data/jobradar/employers.json` | `{employers: [{name, lines[], status, career_url, source_type, ok, listed, matched}]}` |

Et job i `jobs.json` (schema_version 2):

| Felt | Type | Note |
|---|---|---|
| `id` | string | stabilt |
| `company`, `title`, `url` | string | `url` = opslaget hos arbejdsgiveren |
| `job_type` | `"studiejob" \| "praktik" \| "graduate"` | |
| `fit` | `"sikker" \| "sandsynlig" \| "mulig"` | `mulig` = deltid uden klart studie-signal |
| `location` | string | som kilden skriver det |
| `region` | `"storkbh" \| "sjaelland" \| "ukendt"` | |
| `posted` | `"YYYY-MM-DD" \| null` | rigtig opslagsdato, hvis kilden har den |
| `first_seen`, `last_seen` | ISO-tidsstempel | |
| `deadline` | `"YYYY-MM-DD" \| null` | null = løbende |
| `apply_url` | string \| null | arbejdsgiverens ansøgning/opslag |
| `career_url` | string \| null | arbejdsgiverens jobside (reserve) |
| `apply_is_direct` | boolean | |
| `keywords` | string[] | id'er fra `keywords.json` |
| `lines` | string[] | `ha-it`, `ha-almen`, `ha-jura` |
| `description_md` | string | fuld opslagstekst (markdown) |
| `active` | boolean | |
| `source` | string | rekrutteringssystem |
| `details` | object \| mangler | AI-struktureret opslag (se nedenfor). Mangler, hvis jobbet ikke er behandlet endnu |

`details` (alle felter valgfrie undtagen `language`, `summary`, `tasks`, `requirements`):
`language` ("da" | "en" | "other"), `summary` (1-2 sætninger), `tasks` (arbejdsopgaver, liste), `requirements` (hvad de forventer, liste),
`about` (om arbejdspladsen), `offer` (hvad de tilbyder, liste), `hours_per_week`, `start`, `location`, `deadline`,
`contacts` (liste af `{name, title?, phone?, email?}`). Teksten er på opslagets eget sprog.

## 2. Database (allerede migreret 13. oktober 2026)
**`jobs`** – eksisterende kolonner + nye: `job_type text`, `region text`, `keywords text[] not null default '{}'`,
`lines text[] not null default '{}'`, `career_url text`, `apply_is_direct boolean not null default true`.
Gamle kolonner (`tags`, `top50`, `rank`, `origin`, `also_on`, `fit`) bliver stående; sæt `origin = 'employer'` ved synk, brug dem ikke i UI.

**`keywords`** (offentlig læs): `id text pk`, `label text`, `en text`, `"group" text`, `updated_at`. Udfyldt med 57 rækker.

**`study_lines`** (offentlig læs): `id text pk`, `name text`, `school text`, `description text`, `suggested text[]`, `avoid text[]`,
`sort int`, `updated_at`. Udfyldt med `ha-it`, `ha-almen`, `ha-jura`.

**`profiles`** – eksisterende kolonner + nye:
`study_line_id text` (fk → study_lines), `keywords text[]`, `custom_keywords text[]`, `excluded_keywords text[]`,
`excluded_custom text[]`, `job_types text[]` (default alle tre), `regions text[]` (default alle tre), `onboarded_at timestamptz`,
`email_every_days int` (null = ingen mails, ellers 1-30), `email_consent_at timestamptz`, `email_last_sent_at timestamptz`,
`unsubscribe_token uuid` (unik, default `gen_random_uuid()`).
Constraints: når `onboarded_at` er sat, skal `cardinality(keywords) + cardinality(custom_keywords)` være 5-15.
`custom_keywords` og `excluded_custom` højst 5 hver. De gamle kolonner (`interests`, `excluded_fields`, `preferred_locations`, `study_program`) bruges ikke længere.

**Tilføjet 13. oktober (aften):** `jobs.details jsonb`; `profiles.cv_path text`, `cv_uploaded_at timestamptz`, `cv_parsed_at timestamptz`,
`cv_suggested_keywords text[]`. Den eksisterende kolonne `profiles.about` bruges til profilteksten fra CV'et.
Storage-bucket **`cvs`** (privat, maks 5 MB, PDF/DOCX). Brugere kan kun læse/skrive/slette filer under mappen `{deres user id}/`.

**`email_log`** (kun service role): `id bigserial`, `user_id uuid`, `sent_at`, `job_ids text[]`, `ok boolean`, `error text`.

## 3. Match uden AI
For en bruger og et job:
- `hits` = antal af profilens `keywords`, der står i `job.keywords`, + antal `custom_keywords`, der står i titel eller `description_md` (case-insensitivt).
- **Fravalgt**, hvis et `excluded_keywords` står i `job.keywords`, eller et `excluded_custom` står i titlen.
- Kun job med `job_type` i profilens `job_types` og `region` i profilens `regions`.
- "Til dig": `hits ≥ 1` og ikke fravalgt. Sortering: `hits` faldende → frist stigende (løbende sidst) → `first_seen` faldende.
- "Alle job": alt aktivt; fravalgte skjult bag knappen "Vis fravalgte".
- Kortet viser de matchede nøgleord (maks 3, `label` fra `keywords`).
Al logik i `src/lib/match.ts` med vitest-tests. Den skal senere byttes ud med en AI-score uden at røre UI.

## 4. Jobkort
```
[Studiejob]                                       [Frist 15. okt · 4 dage]
Studentermedhjælper til Group Compliance
Tryg · Ballerup
Opslået 3. okt          (eller "Fundet 3. okt", hvis posted mangler)
[Compliance] [GDPR] [Jura]                        ← dine matchede nøgleord
                                  [ Søg hos Tryg → ]
```
- Knappen: hvis `apply_is_direct` → "Søg hos {company}" til `apply_url`; ellers "Gå til {company}s jobside" til `career_url`. Åbner i ny fane.
- Frist rød under 7 dage, "Løbende" hvis null. "Ny"-mærke hvis `first_seen` < 48 timer.
- Ingen beskrivelse på kortet. "Deltid – tjek selv" kun hvis `fit = mulig`.
- Detaljesiden: samme fakta + opslagsteksten foldet sammen ("Vis opslaget").

## 5. Onboarding (første login, før "Til dig")
1. **Studieretning**: et kort pr. række i `study_lines`.
2. **Nøgleord (5-15)**: forudvalgt med retningens `suggested`. Søgefelt over hele `keywords` (søg i `label` og `en`).
   "Tilføj eget ord" (maks 5) med hjælpetekst "Skriv gerne både dansk og engelsk, fx revision / audit". Tæller "8 valgt (5-15)".
3. **Fravalg** (valgfrit): forslag fra retningens `avoid` + eget ord.
4. **Jobtyper og område**: studiejob/praktik/graduate, Storkøbenhavn/hele Sjælland.
5. **E-mail**: "Send mig nye job hver [N] dag(e)" (1-30) eller "Ingen mails" + samtykke-afkrydsning.
Gem og sæt `onboarded_at`. Alt kan ændres på `/profil`.

## 6. E-mail med Resend (studieradar.live)
Forudsætninger, som Valdemar gør selv: Resend-konto, domænet `studieradar.live` verificeret i Resend (DNS-poster hos domæneudbyderen),
secrets `RESEND_API_KEY` og `MAIL_FROM` (fx `Studieradar <job@studieradar.live>`) lagt ind i Lovable Cloud.
- Server-route `src/routes/api/public/send-digests.ts`, beskyttet med `authenticateCronRequest` fra `src/integrations/supabase/cron-auth.ts`.
  pg_cron-jobbet, der kalder den hver time, oprettes af Valdemar (SQL i `docs/sql/`).
- For hver profil med `email_every_days` og `email_consent_at`, hvor der er gået mindst N dage siden `email_last_sent_at`, og klokken er 07-09 dansk tid:
  find aktive job med `first_seen > email_last_sent_at`, `hits ≥ 1`, ikke fravalgt. Ingen job → ingen mail.
- Mail: emne "{antal} nye studiejob til dig", op til 10 job (titel, virksomhed, frist, sted, knap), link til studieradar.live,
  afmeld-link `https://studieradar.live/afmeld?token={unsubscribe_token}`. Dansk HTML + tekstversion.
- Log i `email_log`. Opdatér `email_last_sent_at` kun ved succes.
- Tilstand `MAIL_TEST_TO`: hvis den secret findes, sendes alle mails kun dertil.

---

## Opgaver (én ad gangen, i rækkefølge)

- [x] **Opgave 0 – Opsætning.** Hent denne fil til `docs/STUDIERADAR-SPEC.md`. Tilføj et afsnit øverst i `AGENTS.md`, der siger:
  "Læs docs/STUDIERADAR-SPEC.md før hver opgave. Commit lokalt, push aldrig." Kør `bun install`, `bun run test`, `bun run build`.
- [x] **Opgave 1 – Feed v2.** I `src/lib/sync.server.ts`: skift feed-URL til `…/data/jobradar/jobs.json`, accepter kun `schema_version 2`,
  map de nye felter (afsnit 1 → kolonner i afsnit 2, `origin = 'employer'`). Synk også `keywords.json` → `keywords` og
  `study_lines.json` → `study_lines` (upsert) i samme kørsel. Opdatér `FeedJob`/`FeedFile` i `src/lib/types.ts` og `types.ts` (regel 5).
  Færdig: tests og build lykkes.
- [x] **Opgave 2 – Nyt jobkort og detaljeside** (afsnit 4). Fjern de gamle emne-chips og "Kun store arbejdsgivere".
  Fjern al tekst om Jobindex. Færdig: `grep -ri jobindex src` giver intet.
- [x] **Opgave 3 – Onboarding** (afsnit 5) som ny route `/kom-i-gang`. Brugere uden `onboarded_at` sendes dertil efter login.
- [x] **Opgave 4 – Match og "Til dig"** (afsnit 3) i `src/lib/match.ts` med tests. Forsiden får fanerne "Til dig" og "Alle job",
  filtre for jobtype, område, frist inden for 7 dage og søgning.
- [x] **Opgave 5 – Profilside** (`/profil`) med samme felter som onboarding + e-mail-frekvens og samtykke. Siden `/afmeld?token=`.
- [ ] **Opgave 6 – E-mail-udsendelse** (afsnit 6). Skriv SQL til pg_cron-jobbet i `docs/sql/`.
- [x] **Opgave 7 – Tom tilstand**: ingen match → forslag ("Tilføj flere nøgleord" / "Vis hele Sjælland").
- [x] **Opgave 8 – Arbejdsgiversiden** `/arbejdsgivere`: listen fra `employers.json` med retninger og antal aktive job.

## Runde 2 (efter testrapporten 13. oktober) – se også `docs/TESTRAPPORT.md`

- [ ] **Opgave 9 – Rettelser fra testen.**
  a) Navnet: erstat "Jobradar" med "Studieradar" overalt (logo, `<title>`, meta, tekster). Der findes en anden app, der hedder Job Radar.
  b) Fravalg: på trin 3 og `/profil` skal man kunne vælge **alle** nøgleord fra `keywords` som fravalg (søgefelt som på trin 2), ikke kun retningens forslag.
     Egne fravalg skal matche som delord i titel **og** `description_md` (case-insensitivt), så "revision" også fanger "revisorpraktikant"
     (match på ordstammen: brug de første 6 tegn, hvis ordet er længere end 7). Opdatér `src/lib/match.ts` og tests.
  c) Indlæsning: vis skeleton-kort og skjul "0 aktive opslag", mens job hentes.
  d) `/profil`: fjern onboarding-tekster ("Vi har forvalgt ord …", "Du kan ændre alt på din profil bagefter").
  e) `/afmeld?token=abc`: tokens, der ikke er en gyldig UUID, viser straks ugyldig-beskeden.
- [ ] **Opgave 10 – Login med adgangskode.** Erstat magisk link som standard:
  `/opret` (e-mail, adgangskode min. 8 tegn, gentag) → `supabase.auth.signUp` med `emailRedirectTo` = `https://studieradar.live/kom-i-gang`
  og beskeden "Tjek din mail og bekræft din e-mail". `/login` med e-mail + adgangskode (`signInWithPassword`), fejltekster på dansk
  ("Forkert e-mail eller adgangskode", "Bekræft din e-mail først"). "Glemt adgangskode?" → `resetPasswordForEmail` med redirect til
  `/nulstil-adgangskode`, hvor man vælger ny adgangskode (`updateUser`). Eksisterende brugere uden adgangskode bruger "Glemt adgangskode?".
  Sessionen skal huskes (Supabase gør det som standard – tjek at intet logger ud ved genindlæsning).
## AI i appen: Lovable AI (besluttet 13. oktober)
AI kører i appen via **Lovable AI** (indbygget gateway, nøglen `LOVABLE_API_KEY` styres af Lovable – ingen egen API-nøgle).
- **Model: `google/gemini-3.1-flash-lite`** til både strukturering af opslag og CV-læsning. Det er Lovables anbefalede billige model
  til opsummering/udtræk. Skift kun model ét sted (`AI_MODEL` i `src/lib/ai.server.ts`).
- **Pris (POC):** ca. 3.000 tokens ind + 500 ud pr. opslag ≈ 0,1-0,3 øre … under 0,01 USD. 80 job nu + ca. 100 nye om ugen ≈ 1-2 credits om måneden,
  som dækkes af Lovables gratis AI-grant på 4 credits/måned. Se faktisk forbrug under **Cloud → AI → Recent requests**.
- **CV'er:** PDF-teksten udtrækkes på serveren (npm-pakken `unpdf`) og sendes som tekst – billigere end at sende PDF'en til en dyrere model.
- **Struktureret output:** brug gatewayens OpenAI-kompatible chat-API med et `tools`-skema og `tool_choice`, så svaret altid er gyldig JSON. Validér med zod.
- **Persondata:** CV-tekst sendes til modeludbyderen (Google) via Lovable. Nævn det i privatlivsteksten ved upload.
- Scraperens egen AI-strukturering (`scraper/enrich.py`) er slået fra (ingen nøgle) og bruges ikke.

Databasen er klar: `jobs.details jsonb`, `details_hash text`, `details_model text`, `details_at timestamptz`, `details_error text`.

- [ ] **Lovable-prompt L – Slå Lovable AI til** (gøres i Lovable-editoren, ikke Claude Code – kun Lovable kan oprette nøglen). Se teksten i chatten / afsnittet "Lovable-prompt L" nederst.
- [ ] **Opgave 11 – Struktureret jobside med Lovable AI.** (Kræver at Lovable-prompt L er kørt og pullet.)
  a) **Synken må ikke overskrive AI-felterne:** `details*`-kolonnerne udelades af upsert i `src/lib/sync.server.ts`.
  b) **Berigelse:** `src/lib/enrich.server.ts` med `enrichPendingJobs(limit = 25)`: vælg aktive job, hvor `details is null` eller
     `details_hash` ≠ sha1(titel + description_md). Kald `callAiJson` (fra `ai.server.ts`) med titel, virksomhed, sted og de første 12.000 tegn af
     `description_md`. Skema: `language` ("da"|"en"|"other"), `summary` (1-2 sætninger), `tasks[]`, `requirements[]`, `about`, `offer[]`,
     `hours_per_week`, `start`, `location`, `deadline` (YYYY-MM-DD), `contacts[]` ({name, title?, phone?, email?}).
     Instruks til modellen: skriv på opslagets eget sprog, kun info fra opslaget, maks 7 korte punkter pr. liste, ignorér menutekst fra hjemmesiden,
     kontakter kun hvis opslaget nævner dem som kontakt. Gem `details`, `details_hash`, `details_model`, `details_at`; ved fejl `details_error`.
     Mangler jobbet frist, og modellen fandt en, så sæt `deadline`.
  c) **Kørsel:** kald `enrichPendingJobs(25)` til sidst i `runJobSync()` (den kører hver time). Så behandles nye job automatisk, og prisen er bundet
     til antallet af nye job. Log antallet i `sync_runs` (ny tekst i `error`-feltet er ok, eller tilføj intet skema – brug konsollen).
  d) **Detaljeside og kort:** som beskrevet her: øverst titel, badges og en **kontaktboks** (navn, titel, telefon som `tel:`, e-mail som `mailto:`)
     hvis `details.contacts` findes; fakta (virksomhed, sted, frist, opslået/fundet, timer, start); `summary`; sektionerne **Arbejdsopgaver**,
     **Hvad de forventer**, **Om arbejdspladsen**, **Det tilbyder de** – kun dem med indhold. Mærke "Opslaget er på engelsk" ved `language = en`.
     **Ingen fuld originaltekst** – kun knappen til arbejdsgiveren. Mangler `details`: "Vi har ikke læst opslaget endnu" + knappen.
     Jobkortet viser `summary` som én linje under titlen.
- [ ] **Opgave 12 – CV-upload med Lovable AI.** (Kræver Lovable-prompt L.)
  På `/profil` (og som valgfrit trin i onboarding): sektion "Dit CV" – upload PDF (maks 5 MB) til bucket `cvs` som `{user_id}/cv.pdf`.
  Server-funktion (kræver login): hent filen med service role, udtræk tekst med `unpdf`, kald `callAiJson` med teksten (maks 15.000 tegn) og listen
  af nøgleord fra `keywords` (id + label + en). Skema: `suggested_keywords` (op til 10 id'er fra listen), `custom_keywords` (op til 5 egne ord),
  `profile_text` (3-4 linjer på dansk om uddannelse, erfaring og kompetencer). Gem i `cv_suggested_keywords`, `about`, `cv_uploaded_at`, `cv_parsed_at`.
  UI: "Vi fandt disse kompetencer i dit CV" som chips, der tilføjes med ét klik (stadig maks 15). Profilteksten kan redigeres. "Slet mit CV" fjerner
  filen og nulstiller felterne. Privatlivstekst: "Dit CV gemmes, så vi kan matche job bedre. Teksten behandles af en AI-model hos vores
  leverandør. Du kan slette det når som helst."

## Lovable-prompt L (indsæt i Lovable-editoren)
```
Enable Lovable AI for this project. Do not build any user-facing feature.
Create one server-only helper, src/lib/ai.server.ts, exporting:
  export const AI_MODEL = "google/gemini-3.1-flash-lite";
  export async function callAiJson<T>(opts: { system: string; user: string; schemaName: string; schema: object }): Promise<T>
It must call the Lovable AI gateway with LOVABLE_API_KEY using tool calling (one tool = schemaName with the given JSON schema,
tool_choice forcing that tool), return the parsed tool arguments, throw a clear Error on 402 (out of credits) and 429 (rate limit),
and never be imported from client code. Add a short comment block at the top explaining how to use it.
Keep everything else unchanged. Commit message: "Lovable AI: server-hjælper til struktureret output".
```

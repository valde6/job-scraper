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

- [ ] **Opgave 0 – Opsætning.** Hent denne fil til `docs/STUDIERADAR-SPEC.md`. Tilføj et afsnit øverst i `AGENTS.md`, der siger:
  "Læs docs/STUDIERADAR-SPEC.md før hver opgave. Commit lokalt, push aldrig." Kør `bun install`, `bun run test`, `bun run build`.
- [ ] **Opgave 1 – Feed v2.** I `src/lib/sync.server.ts`: skift feed-URL til `…/data/jobradar/jobs.json`, accepter kun `schema_version 2`,
  map de nye felter (afsnit 1 → kolonner i afsnit 2, `origin = 'employer'`). Synk også `keywords.json` → `keywords` og
  `study_lines.json` → `study_lines` (upsert) i samme kørsel. Opdatér `FeedJob`/`FeedFile` i `src/lib/types.ts` og `types.ts` (regel 5).
  Færdig: tests og build lykkes.
- [ ] **Opgave 2 – Nyt jobkort og detaljeside** (afsnit 4). Fjern de gamle emne-chips og "Kun store arbejdsgivere".
  Fjern al tekst om Jobindex. Færdig: `grep -ri jobindex src` giver intet.
- [ ] **Opgave 3 – Onboarding** (afsnit 5) som ny route `/kom-i-gang`. Brugere uden `onboarded_at` sendes dertil efter login.
- [ ] **Opgave 4 – Match og "Til dig"** (afsnit 3) i `src/lib/match.ts` med tests. Forsiden får fanerne "Til dig" og "Alle job",
  filtre for jobtype, område, frist inden for 7 dage og søgning.
- [ ] **Opgave 5 – Profilside** (`/profil`) med samme felter som onboarding + e-mail-frekvens og samtykke. Siden `/afmeld?token=`.
- [ ] **Opgave 6 – E-mail-udsendelse** (afsnit 6). Skriv SQL til pg_cron-jobbet i `docs/sql/`.
- [ ] **Opgave 7 – Tom tilstand**: ingen match → forslag ("Tilføj flere nøgleord" / "Vis hele Sjælland").
- [ ] **Opgave 8 – Arbejdsgiversiden** `/arbejdsgivere`: listen fra `employers.json` med retninger og antal aktive job.

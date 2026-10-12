# Jobradar-appen – specifikation til kode-agenter

App-repo: `valde6/findmy-denmark-jobs` (Lovable, TanStack Start + Lovable Cloud/Supabase).
Læs også appens egen `AGENTS.md` (typer i `src/lib/types.ts`, data i `src/hooks/`, sync i `src/lib/sync.server.ts`).
Opgaverne står nederst (A1-A9). Tag én ad gangen, i rækkefølge.

## Princip: hurtigt overblik, ingen lange tekster
Jobradar findes, fordi studerende ikke gider læse lange opslag på LinkedIn/Jobindex. Hvert job skal kunne
vurderes på 3 sekunder: **hvad, hvem, hvor, hvornår, og en knap til arbejdsgiverens egen ansøgning.**
Appen må **aldrig** linke til eller nævne Jobindex.

## 1. Datakontrakt (scraperen → appen)
Scraperen (`valde6/job-scraper`, workflow `jobradar-scrape`, hver 3. time) udgiver:

| Fil | Indhold |
|---|---|
| `https://raw.githubusercontent.com/valde6/job-scraper/main/data/jobradar/jobs.json` | `{schema_version: 2, generated_at, counts, jobs[]}` |
| `…/data/jobradar/keywords.json` | `{keywords: [{id, label, en, group}]}` – ordbogen brugerne vælger fra |
| `…/data/jobradar/study_lines.json` | `{study_lines: [{id, name, school, description, suggested[], avoid[]}]}` |
| `…/data/jobradar/employers.json` | `{employers: [{name, lines[], status, career_url, source_type, ok, listed, matched}]}` |

Et job (schema_version 2):

| Felt | Type | Note |
|---|---|---|
| `id` | text | stabilt |
| `company`, `title` | text | |
| `job_type` | `studiejob` \| `praktik` \| `graduate` | |
| `fit` | `sikker` \| `sandsynlig` \| `mulig` | hvor sikkert det er et studiejob (kun relevant for `studiejob`) |
| `location` | text | som kilden skriver det |
| `region` | `storkbh` \| `sjaelland` \| `ukendt` | `ukendt` = kilden siger bare "Danmark" |
| `posted` | date \| null | rigtig opslagsdato, hvis kilden har den |
| `first_seen`, `last_seen` | timestamp | hvornår scraperen så jobbet første/seneste gang |
| `deadline` | date \| null | null = løbende |
| `apply_url` | text \| null | arbejdsgiverens eget opslag/ansøgning |
| `career_url` | text \| null | arbejdsgiverens jobside (reserve) |
| `apply_is_direct` | bool | |
| `keywords` | text[] | id'er fra `keywords.json`, fundet i titel + tekst (dansk og engelsk) |
| `lines` | text[] | studieretninger arbejdsgiveren er relevant for (`ha-it`, `ha-almen`, `ha-jura`) |
| `description_md` | text | fuld opslagstekst (til AI senere). Vises kun foldet ud på detaljesiden |
| `active` | bool | |
| `source` | text | rekrutteringssystem (aldrig `jobindex`) |

## 2. Database (ændringer)
- `jobs`: tilføj `job_type text`, `region text`, `keywords text[]`, `lines text[]`, `career_url text`, `apply_is_direct bool`.
  Behold gamle kolonner indtil videre (`tags`, `top50`, `rank`, `origin`, `also_on`) men brug dem ikke i UI.
- `study_lines` (id pk, name, school, description, suggested text[], avoid text[], sort int) – synkes fra `study_lines.json`. Offentlig læs.
- `keywords` (id pk, label, en, "group") – synkes fra `keywords.json`. Offentlig læs.
- `profiles`: tilføj
  `study_line_id text references study_lines`, `keywords text[]` (5-15 id'er), `custom_keywords text[]` (fritekst, maks 5),
  `excluded_keywords text[]` (id'er), `excluded_custom text[]` (fritekst, maks 5),
  `job_types text[] default '{studiejob,praktik,graduate}'`, `regions text[] default '{storkbh,sjaelland,ukendt}'`,
  `onboarded_at timestamptz`,
  `email_every_days int` (null = ingen mails, 1-30), `email_consent_at timestamptz`, `email_last_sent_at timestamptz`,
  `unsubscribe_token uuid default gen_random_uuid()`.
  Constraint: `cardinality(keywords) between 5 and 15` når `onboarded_at` er sat.
- `email_log` (id, user_id, sent_at, job_ids text[], ok bool, error text). Kun service role.

## 3. Match uden AI (indtil AI-scoren kommer)
Deterministisk og forklarligt. For en bruger og et job:
- `hits` = profilens `keywords` ∩ `job.keywords` + antal `custom_keywords`, der står i titel eller tekst (case-insensitivt).
- **Fravalgt**, hvis et `excluded_keywords` står i `job.keywords`, eller et `excluded_custom` står i titlen.
- Filtrér på profilens `job_types` og `regions`.
- Sortering i "Til dig": `hits` faldende → frist stigende (løbende sidst) → `first_seen` faldende.
- "Til dig" viser job med `hits ≥ 1` og ikke fravalgt. "Alle job" viser alt (fravalgte bag "Vis fravalgte").
- Kortet viser de matchede nøgleord (maks 3 chips, label fra `keywords`).
Læg logikken ét sted (`src/lib/match.ts`) med unit tests – den skal senere erstattes af AI-scoren uden at røre UI.

## 4. Jobkort (listen)
```
[Studiejob]                                         [Frist 15. okt · 4 dage]
Studentermedhjælper til Group Compliance
Tryg · Ballerup
Opslået 3. okt   (eller "Fundet 3. okt", hvis posted mangler)
[Compliance] [GDPR] [Jura]                          ← dine matchede nøgleord
                                    [ Søg hos Tryg → ]
```
- Knap: `apply_is_direct` → "Søg hos {company}" til `apply_url`. Ellers "Gå til {company}s jobside" til `career_url`. Ny fane.
- Frist: rød under 7 dage, "Løbende" hvis null. "Ny"-mærke hvis `first_seen` < 48 t.
- Ingen beskrivelse på kortet. Ingen kildeangivelse, der nævner andre jobportaler.

## 5. Onboarding (efter første login, før "Til dig")
1. **Studieretning**: kort for hver række i `study_lines` (HA (it.), HA Almen, HA Jura). Generelt bygget – nye retninger kommer fra data.
2. **Nøgleord (5-15)**: forudvalgt med retningens `suggested` (brugeren fjerner/tilføjer). Søgefelt over hele ordbogen
   (søg i både `label` og `en`). "Tilføj eget ord" (fritekst, maks 5) med hjælpetekst: "Skriv gerne både dansk og engelsk, fx revision / audit".
   Tæller "8 af 5-15 valgt". Knappen er deaktiveret uden for intervallet.
3. **Fravalg**: forslag fra retningens `avoid` + fritekst. Valgfrit.
4. **Jobtyper og område**: studiejob/praktik/graduate (alle valgt), Storkøbenhavn / hele Sjælland.
5. **E-mail**: "Send mig nye job hver [N] dag(e)" (1-30, forvalg 1) eller "Ingen mails". Samtykke-afkrydsning (påkrævet for mails).
Alt kan ændres senere på `/profil`.

## 6. E-mail med Resend
Forudsætninger (brugeren gør selv): Resend-konto, verificeret domæne, secret `RESEND_API_KEY` og `MAIL_FROM` i Lovable Cloud.
Indtil domænet er verificeret, kan Resend kun sende til kontoejerens egen adresse – byg en `MAIL_TEST_TO`-tilstand.
- Server-route `/api/public/send-digests`, beskyttet med `authenticateCronRequest` (`src/integrations/supabase/cron-auth.ts`), kaldt af pg_cron hver time.
- For hver profil med `email_every_days` og samtykke, hvor `now - email_last_sent_at ≥ N dage` og klokken er 07-09 dansk tid:
  find aktive job med `first_seen > email_last_sent_at`, `hits ≥ 1`, ikke fravalgt. Ingen job → ingen mail (men tjek igen næste dag).
- Mail: emne "{antal} nye studiejob til dig", op til 10 job (titel, virksomhed, frist, sted, knap "Søg hos …"), link til appen,
  afmeld-link `/afmeld?token={unsubscribe_token}` og "Skift frekvens"-link. Dansk, enkel HTML + tekstversion.
- Log i `email_log`, opdatér `email_last_sent_at` kun ved succes. Maks 1 mail pr. bruger pr. døgn uanset fejl.

## 7. Juridisk
- Ingen Jobindex-data, -links eller -omtale i appen.
- Vis arbejdsgiverens tekst sparsomt (foldet ud på detaljesiden). Primær handling er altid linket til arbejdsgiveren.
- E-mail kræver aktivt samtykke og nem afmelding i hver mail.

---

## Opgaver
- [ ] **A1. Feed v2.** Skift `FEED_URL` til `data/jobradar/jobs.json`, accepter `schema_version 2`, migrér `jobs` (afsnit 2), opdatér `FeedJob`-typen.
  Synk også `keywords.json` → `keywords` og `study_lines.json` → `study_lines` i samme kørsel. Færdig: `/status` viser v2-kørsler uden fejl.
- [ ] **A2. Ryd Jobindex-data.** Migration: `delete from user_jobs where job_id in (select id from jobs where origin = 'jobindex'); delete from jobs where origin = 'jobindex';`
  Fjern al UI-tekst om Jobindex ("Fundet via Jobindex"). Færdig: `grep -ri jobindex src` giver intet.
- [ ] **A3. Nyt jobkort + detaljeside** (afsnit 4). Fjern fit-badges fra kortet (vis kun for `mulig`: "Deltid – tjek selv"). Færdig: skærmbillede på mobil og desktop.
- [ ] **A4. Profil-skema + onboarding** (afsnit 2 og 5). Færdig: ny bruger kan ikke se "Til dig" før onboarding; constraint på 5-15 nøgleord virker.
- [ ] **A5. Match + "Til dig"** (afsnit 3) i `src/lib/match.ts` med tests (vitest). Faner: "Til dig" / "Alle job". Filtre: jobtype, område, frist inden for 7 dage, søg.
- [ ] **A6. E-mail-indstillinger** på `/profil` (frekvens 1-30 dage / ingen, samtykke) + `/afmeld?token=`-side.
- [ ] **A7. Udsendelse med Resend** (afsnit 6). Kræver at brugeren har lagt `RESEND_API_KEY` ind. Start i `MAIL_TEST_TO`-tilstand.
- [ ] **A8. Tom tilstand og fejl**: ingen match → forslag ("Tilføj flere nøgleord" / "Udvid til hele Sjælland").
- [ ] **A9. Arbejdsgiver-side** (`/arbejdsgivere`): listen fra `employers.json` med retninger og antal aktive job – viser dækningen ærligt.

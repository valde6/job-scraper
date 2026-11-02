"""Enhedstests af filtrene. De er projektets 'definition' af et studiejob – ret testene, når definitionen ændres."""
import pytest

from scraper.common import student_fit, is_cph, is_denmark, topic_tags, find_deadline, html_to_md, Job


@pytest.mark.parametrize("title,text,expected", [
    ("Studentermedhjælper til Group Finance", "", "sikker"),
    ("Student Assistant – Data & Analytics", "", "sikker"),
    ("Studiejob som analytiker", "", "sikker"),
    ("Praktikant i Marketing", "", None),                       # praktik er ikke studiejob
    ("Graduate Programme 2027", "", None),
    ("Senior Data Analyst", "15-20 timer om ugen", None),       # senior udelukkes
    ("Analytiker", "Du læser en relevant kandidat ved siden af jobbet og kan arbejde 15-20 timer om ugen", "sandsynlig"),
    ("Analytiker (deltid)", "Vi tilbyder et spændende job", "mulig"),
    ("Projektleder", "Fuldtidsstilling 37 timer", None),
])
def test_student_fit(title, text, expected):
    assert student_fit(title, text) == expected


@pytest.mark.parametrize("loc,expected", [
    ("København K", True), ("Kgs. Lyngby", True), ("Frederiksberg", True),
    ("Aarhus C", False), ("Odense", False),
])
def test_is_cph(loc, expected):
    assert is_cph(loc) is expected


def test_is_denmark():
    assert is_denmark("Copenhagen, Denmark")
    assert not is_denmark("Berlin, Germany")


def test_topic_tags_basic():
    tags = topic_tags("Student Assistant", "Du skal arbejde med SQL, Power BI og automatisering af rapporter")
    assert {"SQL", "Power BI / Excel", "Automatisering"} <= set(tags)


def test_topic_tags_lean():
    # regressionstest: 'lean' matchede ikke pga. dobbelt-escapet \\b i regex
    assert "Proces" in topic_tags("Studentermedhjælper", "Erfaring med Lean og forbedringsarbejde")


def test_consulting_excludes_sales_consultant():
    assert "Consulting" not in topic_tags("Salgskonsulent", "Bliv salgskonsulent hos os")
    assert "Consulting" in topic_tags("Student Consultant", "management consulting")


@pytest.mark.parametrize("text,expected", [
    ("Ansøgningsfrist: 15. oktober 2026", "2026-10-15"),
    ("Deadline: 1/11/2026", "2026-11-01"),
    ("Søg senest 3. nov.", "2026-11-03"),
    ("Ingen frist nævnt", None),
    # 21/10: "senest" om tiltrædelse er ikke en frist (Jyske Bank stod med frist 1. jan. 2027 i stedet for 29.10.2026)
    ("Gerne med start senest 1. januar 2027. Ansøgningsfristen er 29.10.2026.", "2026-10-29"),
    ("Vi forventer at byde vores nye kollega velkommen senest d. 1. december 2026.", None),
    ("Applications must be received by **31 October 2026.**", "2026-10-31"),
    ("Applications must be received by **22nd October 2026**.", "2026-10-22"),
    # 21/10: formuleringer og layouts, der gav "ingen frist" for ca. 25 aktive job
    ("Selskab\n\nJyske Bank\n\nAnsøgningsfrist\n\n03.11.2026\n\nEr du en nysgerrig", "2026-11-03"),
    ("Please apply for the Student Assistant Communications role by **22 October 2026**.", "2026-10-22"),
    ("Contact us or submit your application by 28 October 2026. We look forward", "2026-10-28"),
    ("**Application deadline:** October 25, 2026. Applications will be reviewed", "2026-10-25"),
    ("Please submit your online application no later than **31 October 2026 (23:59 Danish time)**.", "2026-10-31"),
    ("**Deadline**\n\n***26 October 2026***. Applications are reviewed on an ongoing basis", "2026-10-26"),
    ("Annonce slut: 03.11.2026", "2026-11-03"),
    ("The application deadline is 2nd of November 2026.\n\n### Info\n\n**Application deadline:** 09-11-2026", "2026-11-09"),
    ("Vi forventer opstart 10.09.2027.", None),
    ("Apply by clicking the button below.", None),
    ("Send your application, CV, and other relevant documents before the 1st of November, 2026. We process", "2026-11-01"),
])
def test_find_deadline(text, expected):
    assert find_deadline(text, 2026) == expected


def test_html_to_md():
    md = html_to_md("<h2>Om jobbet</h2><p>Linje 1&#xa;Linje 2</p><script>x()</script>")
    assert "## Om jobbet" in md and "Linje 2" in md and "x()" not in md


def test_job_id_is_stable():
    a = Job(company="LEGO Group", title="Student", url="https://x/1", external_id="123")
    b = Job(company="lego group", title="Andet navn", url="https://x/2", external_id="123")
    assert a.id == b.id and len(a.id) == 12


def test_html_to_md_keeps_text_after_unclosed_br():
    # regression: med html.parser blev alt efter <br><br> slugt (Workday-opslag mistede det meste af teksten)
    html = "Intro<br><br>Mere tekst<p style='color:red'><span>You must be currently enrolled at a university</span></p>"
    md = html_to_md(html)
    assert "currently enrolled" in md and "Mere tekst" in md


def test_intern_only_as_english_noun():
    from scraper.common import job_type, set_job_types
    set_job_types({"studiejob", "praktik", "graduate"})
    assert job_type("Intern - Finance") == "praktik"
    assert job_type("Summer Intern") == "praktik"
    assert job_type("Intern for Group Treasury") == "praktik"
    assert job_type("Intern sælger til håndværkere") is None
    assert job_type("Kvalitetssygeplejerske med fokus på intern kontrol") is None


def test_department_for_students_is_not_a_student_job():
    from scraper.common import job_type, set_job_types
    set_job_types({"studiejob", "praktik", "graduate"})
    assert job_type("International Partnership Manager (barselsvikar) - Afd. for Uddannelse og Studerende",
                    "Afdelingen for Uddannelse og Studerende søger …") is None
    assert job_type("Studerende til kundeservice", "Vi søger studerende 15 timer om ugen") == "studiejob"


def test_region_outside_zealand_regions():
    from scraper.common import region
    assert region("Region Syddanmark") is None
    assert region("Region Midtjylland") is None
    assert region("Region Hovedstaden") == "storkbh" or region("Region Hovedstaden") == "sjaelland"
    assert region("Hele landet (inkl. Færøerne)") is None


def test_retail_and_service_jobs_are_not_studiejob():
    """17/10: butiks-/servicejob fra Coop, Bestseller, DSB 7-Eleven kom med som "studiejob" via sitemap-kilderne."""
    from scraper.common import job_type
    for t in ["Salgsassistent, SuperBrugsen Egebjerg Købmandsgård, Amagerbrogade",
              "Studerende til kiosk, over 18 år, Kvickly Sundby",
              "Region Hovedstaden Servicemedarbejder deltid, under 18 år, 365discount",
              "Salgsassistenter til DSB 7-Eleven Holbæk Station (15 timer)",
              "PIECES Holbæk - Sales Assistant 25 timer per uge", "Sales Advisor Rødovre",
              "Ufaglærte laboratoriemedhjælpere til studiejob, weekend- og ferieafløsning, samt sabbatår",
              # 21/10: museums-/biografbutik og billetsalg
              "Cinemateket søger løbende studentermedhjælpere til butiks- og billetskranken",
              "Vi søger flere studerende til Butik, Billet & Gæsteservice på Statens Naturhistoriske Museum"]:
        assert job_type(t) is None, t
    for t in ["Studentermedhjælper, marketing, hovedkontoret, Albertslund", "Student Assistant - HR Coordinator, GEM",
              "Studentermedhjælper til Category Management", "Student Assistant to Customer Service Excellence",
              "Studentermedhjælper til Business Development i Claims Center"]:
        assert job_type(t) == "studiejob", t


def test_region_more_towns_and_postcodes():
    """18/10: Eurofins i Aabybro/Vejen og Orkla i Søndersø stod som 'ukendt' i stedet for uden for Sjælland."""
    from scraper.common import region
    assert region("Aabybro, dk") is None and region("Vejen, dk") is None and region("Søndersø, dk") is None
    assert region("Hovedgaden 1, 8600 Silkeborg") is None
    assert region("Vestensborg Allé 78 4800 Nykøbing F") == "sjaelland"
    assert region("Holmen, 1433 København K") == "storkbh"
    assert region("Danmark") == "ukendt"
    assert region("Give Away Street, København") == "storkbh"        # "give" kun som helt ord
    assert region("Gentofte") == "storkbh" and region("Kolding Storcenter") is None


def test_region_compound_jutland_names():
    from scraper.common import region
    for loc in ["Sønderjylland", "Region Nordjylland", "Sydfyn", "Midtjylland, Danmark"]:
        assert region(loc) is None, loc


def test_region_town_names_inside_words():
    """20/10: CBS' "Studerende (IT-vejledere)" blev frasorteret, fordi "vejle" stod inde i "vejledere"."""
    from scraper.common import region
    assert region("Danmark", "Studerende (IT-vejledere) til IT-supporten på Copenhagen Business School") == "storkbh"
    assert region("Danmark", "Studentermedhjælper til Vejle-kontoret") is None


def test_region_foreign_places_without_country_are_outside():
    """21/10: Grant Thornton (HR-Manager) har irske opslag ("Dublin", "Longford") og Scantox (Emply) østrigske. De blev
    "ukendt" og fik arbejdsgiverens region (storkbh/sjaelland), så de stod i appen som job i København."""
    from scraper.common import region
    for loc in ["Dublin", "Longford", "Parkring, 12, 8074, Grambach, Austria", "Stockholm, Sweden", "London", "Hamburg"]:
        assert region(loc) is None, loc
    assert region("Copenhagen, Denmark; London, UK") == "storkbh"        # flere steder, heraf København
    assert region("Malmö eller København") == "storkbh"


def test_region_title_names_copenhagen_or_other_town():
    """21/10: EY's "Graduate - Consulting | Copenhagen & Aarhus" (sted "Danmark") blev frasorteret pga. "Aarhus" i titlen.
    Danmarks Fængslers "Studentermedhjælper til arresthuse i Østjylland" (sted "Region Hovedstaden") kom med."""
    from scraper.common import region
    assert region("Danmark", "Graduate - Consulting | August 2027 | Copenhagen & Aarhus") == "storkbh"
    assert region("Danmark", "Part-time Analyst - Corporate Finance (Copenhagen and Aarhus)") == "storkbh"
    assert region("Danmark", "Finansbachelorpraktikant i Spar Nord og Nykredit på Sjælland") == "sjaelland"
    assert region("Danmark", "Er du vores nye finansbachelorpraktikant i Syddanmark?") is None
    assert region("Region Hovedstaden", "Studentermedhjælper til arresthuse i Østjylland") is None
    assert region("Region Hovedstaden", "Studentermedhjælper til Aarhus og København") == "storkbh"
    assert region("Region Hovedstaden", "Studentermedhjælper til SoMe") == "storkbh"
    assert region("Aarhus", "Student Assistant, Copenhagen team") is None          # stedet vinder over titlen
    assert region("Danmark", "Student Assistant (hybrid)") == "ukendt"


def test_stud_jur_titles_are_studiejob():
    """20/10: advokatfirmaer (Mazanti, Gorrissen, Plesner) slår studiejob op som "stud.jur." uden ordet "student"."""
    from scraper.common import is_student, job_type, set_job_types
    set_job_types({"studiejob", "praktik", "graduate"})
    for t in ["Stud.jur. til M&A-afdelingen", "Stud. jur. til Procedure", "Jurastuderende til vores team i Aarhus",
              "Stud.merc.(jur.) til Skat"]:
        assert is_student(t) and job_type(t) == "studiejob", t
    assert not is_student("Studievejleder til jura")


def test_compound_trainee_graduate_and_plural_interns():
    """21/10: KPMG "Revisortrainee 2027 – Copenhagen", Beierholm "Bliv revisortrainee i 2027 …", PwC "Bliv revisorgraduate
    hos PwC Hellerup …" og Rambøll "Communications Interns" blev frasorteret som "ikke studiejob"."""
    from scraper.common import is_student, job_type, set_job_types
    set_job_types({"studiejob", "praktik", "graduate"})
    for t in ["Revisortrainee 2027 – Copenhagen", "Bliv outsourcingtrainee i 2027 hos Danmarks bedste arbejdsplads for unge",
              "Bliv revisorgraduate hos PwC Hellerup og kom helt tæt på kunderne fra dag 1"]:
        assert job_type(t) == "graduate", t
        assert is_student(t), t                          # generic/hrmanager beholder dem i listen
    assert job_type("Communications Interns") == "praktik"
    assert job_type("Labtrainee til nyt labmiljø - studenterjob på Erhvervsakademi København") == "studiejob"
    assert job_type("Intern kontrol – specialist") is None                  # dansk tillægsord, uændret


def test_profession_titles_are_not_studiejob():
    """21/10: færdiguddannede faggrupper og fleks-/tilkaldejob kom med som studiejob (teksten nævnte studerende + deltid)."""
    from scraper.common import job_type, set_job_types
    set_job_types({"studiejob", "praktik", "graduate"})
    body = "Afdelingen modtager medicinstuderende. Stillingen er på deltid."
    for t in ["Reservelæge søges til Bedøvelse under Afdeling for Bedøvelse, Smerter og Respirationsstøtte",
              "Farmakonom søges til flexjob-ansættelse på Klinisk Farmakologisk Afdeling",
              "Søger du et fleksibelt deltidsarbejde? Bliv timelønnet tilkaldevikar som dyrlæge i Kød-kontrollen",
              "Tandplejer eller tandlæge til traineestilling i tandreguleringen på Saxogade",
              "Pædagogmedhjælper til SFO Nordlys – Skolen på Grundtvigsvej"]:
        assert job_type(t, body) is None, t
    assert job_type("Sygeplejestuderende eller anden sundhedsfaglig studerende til Sølund", body) == "studiejob"
    assert job_type("Er du pædagogstuderende og mangler et weekendjob", body) == "studiejob"
    assert job_type("Studentermedhjælpere i medicin søges til Kompetencecenter for Transkulturel Psykiatri") == "studiejob"


def test_parttime_signal_is_a_whole_word_and_not_fulltime_hours():
    """21/10: ATP "Sagsbehandlere …" blev "mulig" pga. "deltidskontorarbejde" i en sagsbeskrivelse, og DM's
    "Salgskonsulent - deltid" på 32 timer om ugen kom med som studiejob."""
    from scraper.common import student_fit, fulltime_hours
    assert student_fit("Sagsbehandlere til sager om tab af erhvervsevne",
                       "En tømrer går fra fysisk arbejde til deltidskontorarbejde.") is None
    assert student_fit("Salgskonsulent til fagforeningen DM - deltid", "Stillingen er på 32 timer om ugen.") is None
    assert student_fit("Analyst (part-time) - Corporate Finance", "Vi søger en analytiker.") == "mulig"
    assert student_fit("Administrativ medarbejder", "Stillingen er på deltid, 15 timer om ugen.") == "mulig"
    assert fulltime_hours("37 timer om ugen") and not fulltime_hours("15-20 timer om ugen, evt. 37 timer i ferier")


def test_university_teaching_assistants_are_studiejob():
    """21/10: CBS' instruktor-stillinger (kun for indskrevne studerende, deltid) blev frasorteret som "ikke studiejob"."""
    from scraper.common import is_student, job_type, set_job_types
    set_job_types({"studiejob", "praktik", "graduate"})
    for t in ["Instruktor søges til FLØK", "Instruktor til Department of Digitalization",
              "Instructors for Department of Digitalization", "Teaching Assistants (TA) Spring 2027"]:
        assert is_student(t) and job_type(t) == "studiejob", t
    for t in ["Teknisk instruktør med elektrisk baggrund", "Instruktør til skoleoplæringselever, VVS-uddannelsen",
              "Teaching Assistant Professorship in development, fabrication, assembly of mechanical systems",
              "Fitness instructor"]:
        assert job_type(t) is None, t


def test_digital_sales_associate_is_not_retail():
    """21/10: Saxo Banks "Student Digital Sales Associate" (Hellerup) blev frasorteret af butiksfilteret."""
    from scraper.common import job_type, set_job_types
    set_job_types({"studiejob", "praktik", "graduate"})
    assert job_type("Student Digital Sales Associate") == "studiejob"
    assert job_type("Sales Associate, Vero Moda Fisketorvet") is None
    assert job_type("Retail Sales Associate - Warehouse (12-19 Hours/week)") is None


def test_find_deadline_require_year():
    assert find_deadline("Søg senest 3. nov.", 2026, require_year=True) is None
    assert find_deadline("Søg senest 3. nov. 2026", 2026, require_year=True) == "2026-11-03"


def test_ugekontrol_2_november_wrong_jobs_are_filtered():
    """2/11: job, som ugekontrollen markerede, og som stadig var aktive efter natpatchen fra 21/10."""
    from scraper.common import job_type, set_job_types
    set_job_types({"studiejob", "praktik", "graduate"})
    body = "Vi søger studerende på deltid, 15 timer om ugen ved siden af dit studie."
    for t in ["Deltidssælger u/18 år til JYSK KBH K", "Uopfordrede ansøgninger til Deltidssælger o/18 år",
              "Uopfordrede ansøgninger til Store Manager Trainee",
              "Bliv fremtidens leder i Matas – start din karriere som Manager Trainee!",
              "Booking- og SoMe-ansvarlig til Matas Lyngby Storcenter – 12-15 timer om ugen",
              "Weekendafløsere til Plejecenter Damgårdsparken",
              "Teamkoordinator til Brøndbyvester Hjemmepleje - 37 timer uden weekendvagt - genopslag",
              "Greve Kommune søger ledsagere til borgere med nedsat funktionsevne",
              "Administrativ medarbejder til Børneambassaden (Barselsvikariat)",
              "Studielektor i repetition for sangere, akkompagnement for pianister",
              "Bliv en del af vores stærke sekretærteam i Led- og Knoglekirurgi",
              "Serviceminded receptionist til Præhospitalet i Region Østdanmark",
              "Erfaren sekretariatsprofil til ledelsesunderstøttelse i Studenterrådgivningen",
              "IT-supportelev - bliv en del af et stærkt Service Desk-team i en levende uddannelsesverden",
              "Logistik- og indkøbselev til internationale byggeprojekter",
              "Mejeri trainee, Arla foods Branderup mejeri."]:
        assert job_type(t, body) is None, t
    # Det, der skal blive: rigtige studiejob med de samme ord i nærheden
    for t, jt in [("Studentermedhjælper til sekretariatet i Institut for Økonomi", "studiejob"),
                  ("Studentermedhjælper til Center for Ungdomsuddannelser", "studiejob"),
                  ("Management Trainee Programme 2027 – Danske Bank", "graduate"),
                  ("Studentermedhjælper til salg og rådgivning", "studiejob"),
                  ("Sygeplejestuderende til weekendvagter på plejecenter", "studiejob"),
                  ("Studerende til vikariat i kommunikationsafdelingen", "studiejob"),
                  ("Student Assistant, Relevant Analytics", "studiejob")]:
        assert job_type(t, body) == jt, t


def test_region_title_town_outside_zealand_wins_over_hq_address():
    """2/11: Munck "… til Munck Havne & Anlæg, Aalborg" havde hovedkontoret i Glostrup som sted."""
    from scraper.common import region
    assert region("Produktionsvej 24. 2600 Glostrup", "Ingeniørpraktikanter til Munck Havne & Anlæg, Aalborg") is None
    assert region("Copenhagen, Aarhus or Aalborg", "Student Assistant, Netcompany Consulting") == "storkbh"
    assert region("Glostrup", "Studentermedhjælper til vores kontorer i Aarhus og Glostrup") == "storkbh"

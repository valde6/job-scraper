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
              "Ufaglærte laboratoriemedhjælpere til studiejob, weekend- og ferieafløsning, samt sabbatår"]:
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
    assert region("Danmark", "Studerende (IT-vejledere) til IT-supporten på Copenhagen Business School") == "ukendt"
    assert region("Danmark", "Studentermedhjælper til Vejle-kontoret") is None

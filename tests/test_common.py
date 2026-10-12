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

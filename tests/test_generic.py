"""Generisk HTML-adapter: titler og bladring."""
import pytest

from scraper.adapters import generic


@pytest.fixture(autouse=True)
def _robots_ok(monkeypatch):
    monkeypatch.setattr(generic, "robots_allows", lambda url: "/privat/" not in url)


def test_clean_title_soft_hyphen_and_prefix():
    raw = "Om stillingen Stu­dent As­si­stant for seiz­mic Plat­form"
    assert generic.clean_title(raw, r"^Om stillingen\s+") == "Student Assistant for seizmic Platform"
    assert generic.clean_title("Se job Studentermedhjælper") == "Studentermedhjælper"


class R:
    def __init__(self, text):
        self.text = text


def test_pages_stop_when_no_new_links(monkeypatch):
    pages = {
        0: '<a href="/ledigestillinger/studentermedhjaelper-til-hr">Studentermedhjælper til HR</a>'
           '<a href="/ledigestillinger/paedagog-til-vuggestue">Pædagog til vuggestuen</a>',
        1: '<a href="/ledigestillinger/studentermedhjaelper-til-it">Studentermedhjælper til IT</a>',
        2: '<a href="/ledigestillinger/studentermedhjaelper-til-it">Studentermedhjælper til IT</a>',  # samme som side 1
    }
    fetched = []

    def fake_get(url, **kw):
        fetched.append(url)
        n = int(url.rsplit("=", 1)[1])
        return R(pages.get(n, ""))

    monkeypatch.setattr(generic, "get", fake_get)
    monkeypatch.setattr(generic, "detail", lambda company, title, href, dk_only, list_loc="": title)
    listed, jobs = generic.scrape({"name": "Københavns Kommune", "list_urls": ["https://www.kk.dk/ledigestillinger"],
                                   "link_pattern": r"/ledigestillinger/[^?#]+$", "dk_only": True,
                                   "pages": {"param": "page", "start": 0, "max": 10}})
    assert listed == 3
    assert jobs == ["Studentermedhjælper til HR", "Studentermedhjælper til IT"]
    assert len(fetched) == 3                          # side 2 gav ingen nye links → stop


def test_generic_one_bad_detail_page_does_not_fail_source(monkeypatch):
    """17/10: CBS-kilden fejlede helt, fordi ét opslag gav 404."""
    import requests
    from scraper.adapters import generic

    class R:
        def __init__(self, text):
            self.text = text

    listing = ('<a href="/job/studentermedhjaelper-til-hr">Studentermedhjælper til HR</a>'
               '<a href="/job/student-assistant-gone">Student assistant til marketing</a>')

    def g(url, **kw):
        if url.endswith("/job/"):
            return R(listing)
        if "gone" in url:
            raise requests.HTTPError("404 Client Error: Not Found")
        return R("<html><body><h1>Studentermedhjælper til HR</h1><main><p>15 timer om ugen ved siden af dit studie, København.</p></main></body></html>")

    monkeypatch.setattr(generic, "get", g)
    listed, jobs = generic.scrape({"name": "CBS", "list_urls": ["https://x.dk/job/"], "link_pattern": r"/job/[a-z-]+$", "dk_only": True})
    assert listed == 2 and [j.title for j in jobs] == ["Studentermedhjælper til HR"]


def test_title_from_detail(monkeypatch):
    """Mazanti: linkene hedder "Læs mere"; titlen står kun på opslaget. Bech-Bruun: link-teksten har frist og by."""
    pages = {
        "https://m.dk/karriere/ledige-stillinger/":
            '<a href="/karriere/ledige-stillinger/stud-jur-til-ma-afdelingen">Læs mere</a>'
            '<a href="/karriere/ledige-stillinger/advokat-med-erfaring-inden-for-fund-formation">Læs mere</a>',
        "https://m.dk/karriere/ledige-stillinger/stud-jur-til-ma-afdelingen":
            "<html><body><main><h1>Stud.jur. til M&amp;A-afdelingen</h1><p>" + "Som studentermedhjælper " * 20
            + "</p></main></body></html>",
        "https://m.dk/karriere/ledige-stillinger/advokat-med-erfaring-inden-for-fund-formation":
            "<html><body><main><h1>Advokat med erfaring inden for fund formation</h1><p>" + "Erfaren advokat " * 20
            + "</p></main></body></html>",
    }
    monkeypatch.setattr(generic, "get", lambda url, **kw: R(pages[url]))
    listed, jobs = generic.scrape({"name": "Mazanti-Andersen", "list_urls": ["https://m.dk/karriere/ledige-stillinger/"],
                                   "link_pattern": r"/ledige-stillinger/[a-z0-9-]{12,}", "dk_only": True,
                                   "title_from": "detail"})
    assert listed == 2
    assert [j.title for j in jobs] == ["Stud.jur. til M&A-afdelingen"]


def test_generic_respects_robots(monkeypatch):
    pages = {"https://x.dk/job/": '<a href="/privat/studentermedhjaelper-til-hr">Studentermedhjælper til HR</a>'}
    monkeypatch.setattr(generic, "get", lambda url, **kw: R(pages[url]))
    listed, jobs = generic.scrape({"name": "X", "list_urls": ["https://x.dk/job/"], "link_pattern": "/privat/"})
    assert listed == 1 and jobs == []


def test_label_location_jyske_bank():
    """20/10: Jyske Banks opslag har ingen JSON-LD; byen står under "Arbejdssted"."""
    md = ("# Studentermedhjælper til Finance i Jyske Finans\n\n‌\n\nJobområde\n\nUniversitets­studerende\n\n---\n\n"
          "Arbejdssted\n\nSilkeborg\n\nAfdeling\n\nFinance\n\nAnsøgningsfrist\n\n30.10.2026\n")
    assert generic.label_location(md) == "Silkeborg"
    assert generic.label_location("**Arbejdssted:** Odense, Vejle eller Esbjerg\n") == "Odense, Vejle eller Esbjerg"
    assert generic.label_location("Location: Copenhagen\n") == "Copenhagen"
    assert generic.label_location("Vi har kontorer i hele landet.") == ""


def test_detail_uses_label_location(monkeypatch):
    html = ("<html><body><main><h1>Studentermedhjælper til Research</h1><div><p>Arbejdssted</p><p>Silkeborg</p>"
            "<p>" + "Er du analytisk stærk og studerende? " * 10 + "</p></div></main></body></html>")
    monkeypatch.setattr(generic, "get", lambda url, **kw: R(html))
    j = generic.detail("Jyske Bank", "", "https://x/jobopslag?id=1", True)
    assert j.location == "Silkeborg"
    from scraper.common import region
    assert region(j.location, j.title) is None          # frasorteres som uden for Sjælland

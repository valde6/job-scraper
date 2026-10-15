"""Generisk HTML-adapter: titler og bladring."""
from scraper.adapters import generic


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

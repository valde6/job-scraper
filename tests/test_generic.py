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

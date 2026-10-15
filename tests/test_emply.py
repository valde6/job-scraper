"""Emply via karrieresidens eget JSON-kald (uden browser)."""
from scraper.adapters import emply

PAGE_HTML = """<script>
var languageKey = 'da-DK';
var config = { count: 6, filters: [], sectionId: '2248ff4a-0984-4d9a-aeae-b72472653bbd', offset: 0 };
var adLink = '/da/ad/' + vacancy.titleAsUrl + '/' + vacancy.shortId;
</script>"""


class R:
    def __init__(self, text="", data=None):
        self.text, self._data = text, data

    def json(self):
        return self._data


def vac(title, short, content="<p>Studiejob 15 timer om ugen ved siden af dit studie.</p>"):
    return {"title": title, "titleAsUrl": title.lower().replace(" ", "-"), "shortId": short, "talentPool": False,
            "deadline": "2026-11-06T22:59:00Z", "published": "2026-10-14T11:21:28Z", "location": "København, Denmark",
            "translations": [{"title": title, "content": content}]}


def test_emply_json(monkeypatch):
    calls = []
    monkeypatch.setattr(emply, "get", lambda url, **kw: R(PAGE_HTML))

    def fake_post(url, json=None, **kw):
        calls.append(json)
        return R(data={"vacancies": [vac("Studentermedhjælper til HR", "axfdw7"),
                                     vac("Afdelingsleder til økonomi", "zzzz11", "<p>Fuldtid, ledelse.</p>")],
                       "count": 2})

    monkeypatch.setattr(emply, "post", fake_post)
    listed, jobs = emply.scrape({"name": "Folkekirkens Nødhjælp", "url": "https://dca.career.emply.com"})
    assert listed == 2
    assert [j.title for j in jobs] == ["Studentermedhjælper til HR"]
    j = jobs[0]
    assert j.url == "https://dca.career.emply.com/da/ad/studentermedhjælper-til-hr/axfdw7"
    assert j.external_id == j.url                      # samme id som da browser-adapteren hentede opslaget
    assert j.deadline == "2026-11-06" and j.source == "emply"
    assert calls[0]["sectionId"] == "2248ff4a-0984-4d9a-aeae-b72472653bbd" and calls[0]["langCode"] == "da-DK"


def test_emply_falls_back_to_browser(monkeypatch):
    monkeypatch.setattr(emply, "get", lambda url, **kw: R("<html>ingen sektion</html>"))
    monkeypatch.setattr(emply, "_browser", lambda cfg, base: (0, ["browser"]))
    assert emply.scrape({"name": "X", "url": "https://x.career.emply.com"}) == (0, ["browser"])

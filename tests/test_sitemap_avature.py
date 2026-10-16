"""Sitemap-adapteren, Avature-adapteren og extract_posting.

HTML'en er forkortede udgaver af rigtige sider hentet 16/10-2026 (careers.carlsberg.com, careers.tryg.com,
careers.loreal.com, careers.bain.com)."""
from scraper import common
from scraper.adapters import avature, sitemap
from scraper.common import extract_posting


class R:
    def __init__(self, text=""):
        self.text = text


# --- SuccessFactors Career Site Builder: microdata, sted som 'Valby, DK', SF-datoformat
SF_JOB = """<html><head><meta property="og:title" content="Studentermedhjælper til Innovation &amp; Portfolio"/></head>
<body><div class="jobDisplay" itemscope itemtype="http://schema.org/JobPosting">
<span itemprop="jobLocation" itemscope itemtype="http://schema.org/Place"><span itemprop="address" itemscope
 itemtype="http://schema.org/PostalAddress"><meta itemprop="streetAddress" content="Valby, DK"></span></span>
<meta itemprop="datePosted" content="Mon Oct 12 00:00:00 UTC 2026">
<meta itemprop="validThrough" content="Sun Nov 01 23:00:00 UTC 2026">
<meta itemprop="hiringOrganization" content="Carlsberg">
<h1><span itemprop="title" class="jobTitle">Studentermedhjælper til Innovation &amp; Portfolio Carlsberg Danmark, Valby</span></h1>
<span itemprop="description" class="jobdescription"><p>Er du struktureret og nysgerrig? Du læser på en videregående
uddannelse og kan arbejde 15-20 timer om ugen ved siden af dit studie.</p></span></div></body></html>"""

# --- Radancy/TalentBrew: JSON-LD
LD_JOB = """<html><head><script type="application/ld+json">{"@context":"http://schema.org","@type":"JobPosting",
"title":"Nordic People Development & Learning Graduate","datePosted":"2026-10-14",
"description":"<p>Graduate programme in Copenhagen for recent graduates.</p>",
"jobLocation":[{"@type":"Place","address":{"@type":"PostalAddress","addressLocality":"Copenhagen","addressCountry":"DK"}}]}
</script></head><body><h1>Andet</h1></body></html>"""

# --- Avature: etiket/værdi-felter, JSON-LD kun med titel og dato
AV_JOB = """<html><head><title>Student Assistant, Recruiting - 111066</title>
<script type="application/ld+json">{"@context":"https:\\/\\/schema.org\\/","@type":"JobPosting","title":"Student Assistant, Recruiting","datePosted":"2026-10-08"}</script>
</head><body><article>
<div class="article__content__view__field form__item--odd"><div class="article__content__view__field__label"> Job Title </div>
 <div class="article__content__view__field__value"> Student Assistant, Recruiting </div></div>
<div class="article__content__view__field form__item--even"><div class="article__content__view__field__label"> Job ID </div>
 <div class="article__content__view__field__value"> 111066 </div></div>
<div class="article__content__view__field form__item--even"><div class="article__content__view__field__label"> Employment Type </div>
 <div class="article__content__view__field__value"> Temporary Part-Time </div></div>
<div class="article__content__view__field form__item--odd"><div class="article__content__view__field__label"> Location(s) </div>
 <div class="article__content__view__field__value"> Copenhagen </div></div>
<div class="article__content__view__field "><div class="article__content__view__field__value"><p><strong>Bain &amp; Company</strong>
 is looking for a student assistant to support our Nordic recruiting team alongside your studies, 15 hours per week.</p></div></div>
</article></body></html>"""


def test_extract_microdata_successfactors():
    p = extract_posting(SF_JOB)
    assert p["title"].startswith("Studentermedhjælper til Innovation & Portfolio")
    assert p["location"] == "Valby, DK"
    assert p["posted"] == "2026-10-12" and p["deadline"] == "2026-11-01"
    assert "ved siden af dit studie" in p["description_html"]


def test_extract_jsonld():
    p = extract_posting(LD_JOB)
    assert p["title"] == "Nordic People Development & Learning Graduate"
    assert p["location"] == "Copenhagen, DK"
    assert p["posted"] == "2026-10-14"


def test_extract_label_fields_avature():
    p = extract_posting(AV_JOB)
    assert p["title"] == "Student Assistant, Recruiting"      # fra JSON-LD
    assert p["location"] == "Copenhagen"                       # fra felterne (JSON-LD mangler sted)
    assert p["employment_type"] == "Temporary Part-Time"
    assert "Nordic recruiting team" in p["description_html"]


def test_extract_fallback_h1_and_main():
    p = extract_posting("<html><body><nav>menu</nav><main><h1>Studiejob i HR</h1><p>15 timer om ugen</p></main></body></html>")
    assert p["title"] == "Studiejob i HR"
    assert "15 timer" in p["description_html"] and "menu" not in p["description_html"]


# --- sitemap-adapteren
SITEMAP_INDEX = """<?xml version="1.0"?><sitemapindex><sitemap><loc>https://careers.x.com/sitemap1.xml</loc></sitemap></sitemapindex>"""
SITEMAP = """<?xml version="1.0"?><urlset>
<url><loc>https://careers.x.com/CarlsbergDK/job/Valby-Studentermedhjælper-til-Innovation-&amp;-Portfolio/1446335033/</loc></url>
<url><loc>https://careers.x.com/job/Poznan-AP-Intern-with-German/1391378833/</loc></url>
<url><loc>https://careers.x.com/job/Milano-Finance-Manager/1438312633/</loc></url>
<url><loc>https://careers.x.com/job/Ballerup-Senior-Accountant/1444408833/</loc></url>
<url><loc>https://careers.x.com/about-us</loc></url>
</urlset>"""
POZNAN = SF_JOB.replace("Valby, DK", "Poznan, PL").replace("Studentermedhjælper til Innovation &amp; Portfolio Carlsberg Danmark, Valby", "AP Intern with German")
SENIOR = SF_JOB.replace("Valby, DK", "Ballerup, DK").replace("Studentermedhjælper til Innovation &amp; Portfolio Carlsberg Danmark, Valby", "Senior Accountant") \
    .replace("Du læser på en videregående\nuddannelse og kan arbejde 15-20 timer om ugen ved siden af dit studie.", "Fuldtid, 5 års erfaring.")


def _fake_get(pages):
    calls = []

    def g(url, **kw):
        calls.append(url)
        for k, v in pages.items():
            if k in url:
                return R(v)
        raise AssertionError(f"uventet kald: {url}")
    return g, calls


def test_sitemap_adapter(monkeypatch):
    common.REJECTED.clear()
    g, calls = _fake_get({"robots.txt": "User-agent: *\nDisallow: /services/\nSitemap: https://careers.x.com/sitemap.xml",
                          "/sitemap.xml": SITEMAP_INDEX, "/sitemap1.xml": SITEMAP,
                          "1446335033": SF_JOB, "1391378833": POZNAN, "1444408833": SENIOR})
    monkeypatch.setattr(sitemap, "get", g)
    monkeypatch.setattr(common, "get", g)
    common._ROBOTS.clear()
    listed, jobs = sitemap.scrape({"name": "Carlsberg", "url": "https://careers.x.com"})
    assert listed == 4                                   # 4 jobsider i sitemap'en (about-us tæller ikke)
    assert [j.title for j in jobs] == ["Studentermedhjælper til Innovation & Portfolio Carlsberg Danmark, Valby"]
    j = jobs[0]
    assert j.location == "Valby, DK" and j.deadline == "2026-11-01" and j.external_id == "1446335033"
    assert not any("Milano" in c for c in calls)        # hverken studieord eller dansk sted i adressen → hentes ikke
    reasons = {r["title"]: r["reason"] for r in common.REJECTED}
    assert reasons["Senior Accountant"] == "ikke studiejob"
    assert reasons["AP Intern with German"].startswith("uden for Danmark")


def test_sitemap_respects_robots(monkeypatch):
    g, calls = _fake_get({"robots.txt": "User-agent: *\nDisallow: /CarlsbergDK/", "/sitemap.xml": SITEMAP, "1446335033": SF_JOB})
    monkeypatch.setattr(sitemap, "get", g)
    monkeypatch.setattr(common, "get", g)
    common._ROBOTS.clear()
    listed, jobs = sitemap.scrape({"name": "X", "url": "https://careers.x.com"})
    assert jobs == [] and not any("1446335033" in c for c in calls)


def test_sitemap_url_place_fallback():
    assert sitemap.url_place("https://careers.coloplast.com/job/Humlebæk-AI-Assistant-(Student-Assistant)/1445560733/") == "Humlebæk"
    assert sitemap.dk("Humlebæk") and not sitemap.dk("Auckland, New Zealand")


# --- Avature-adapteren
def _card(href, title, loc):
    return f"""<article class="article article--result"><div class="article__header"><div class="article__header__text">
<h3 class="article__header__text__title"><a href="{href}"> {title} </a></h3>
<div class="article__header__text__subtitle"><span> {loc} </span></div></div>
<div class="article__header__actions"><a class="button button--secondary" href="{href}">Learn more</a>
<a class="shareButton" href="https://careers.bain.com/_linkedinApiv2?shareUrl=https%3A%2F%2Fcareers.bain.com%2Fjobs%2FFolderDetail%2FX%2F1">LinkedIn</a>
</div></div></article>"""


PAGE1 = "<html><body>" + _card("https://careers.bain.com/jobs/FolderDetail/Accountant-General-Accounting/110080", "Accountant, General Accounting", "Mexico City") \
    + _card("https://careers.bain.com/jobs/FolderDetail/Student-Assistant-Recruiting/111066", "Student Assistant, Recruiting", "Copenhagen") \
    + _card("/jobs/FolderDetail/Expert-Manager-Software-Engineering-Copenhagen/106582", "Expert Manager, Software Engineering", "Copenhagen") + "</body></html>"
MANAGER = AV_JOB.replace("Student Assistant, Recruiting", "Expert Manager, Software Engineering") \
    .replace("Temporary Part-Time", "Full-Time").replace("is looking for a student assistant to support our Nordic recruiting team alongside your studies, 15 hours per week.", "seeks a manager with 10 years of experience.")


def test_avature_adapter(monkeypatch):
    calls = []

    def g(url, params=None, **kw):
        calls.append((url, (params or {}).get("folderOffset")))
        if "SearchJobs" in url:
            return R(PAGE1 if params["folderOffset"] == 0 else "<html><body>Ingen flere</body></html>")
        if "111066" in url:
            return R(AV_JOB)
        if "106582" in url:
            return R(MANAGER)
        raise AssertionError(url)

    monkeypatch.setattr(avature, "get", g)
    listed, jobs = avature.scrape({"name": "Bain & Company", "url": "https://careers.bain.com/jobs"})
    assert listed == 3
    assert [j.title for j in jobs] == ["Student Assistant, Recruiting"]
    j = jobs[0]
    assert j.url == "https://careers.bain.com/jobs/FolderDetail/Student-Assistant-Recruiting/111066"
    assert j.location == "Copenhagen" and j.external_id == "111066" and j.posted == "2026-10-08"
    assert not any("110080" in c[0] for c in calls)      # Mexico City: detaljesiden hentes ikke
    assert [c[1] for c in calls if "SearchJobs" in c[0]] == [0, 10]   # stopper, når en side ikke har nye opslag

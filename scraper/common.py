"""Fælles hjælpefunktioner: HTTP, tekstrensning, filtre."""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36 job-scraper (personal use)"
)

_session = requests.Session()
_session.headers.update({"User-Agent": UA, "Accept-Language": "da,en;q=0.8"})


def http(method: str, url: str, *, retries: int = 2, **kw) -> requests.Response:
    kw.setdefault("timeout", 25)
    last = None
    for attempt in range(retries + 1):
        try:
            r = _session.request(method, url, **kw)
            if r.status_code in (429, 502, 503, 504) and attempt < retries:
                time.sleep(2 + attempt * 3)
                continue
            r.raise_for_status()
            return r
        except requests.RequestException as e:  # noqa: PERF203
            last = e
            if attempt < retries:
                time.sleep(1.5 + attempt * 2)
    raise last  # type: ignore[misc]


def get(url: str, **kw) -> requests.Response:
    return http("GET", url, **kw)


def post(url: str, **kw) -> requests.Response:
    return http("POST", url, **kw)


# ---------------------------------------------------------------- tekst
def html_to_md(html: str | None) -> str:
    if not html:
        return ""
    html = re.sub(r"&#x[aA];|&#10;", "\n", html)
    md = markdownify(html, heading_style="ATX", strip=["img", "script", "style"])
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()


def soup(html: str) -> BeautifulSoup:
    import warnings
    from bs4 import XMLParsedAsHTMLWarning
    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
    return BeautifulSoup(html, "lxml")


def clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


# ---------------------------------------------------------------- filtre
STUDENT_RE = re.compile(
    r"student|studerende|studiejob|studie-job|studentermedhj|studentermedarb|"
    r"studentmedhj|working\s+student|werkstudent|part[- ]time\s+student",
    re.I,
)
# ting der ligner studenterjob men ikke er det
EXCLUDE_RE = re.compile(
    r"graduate\s+program|graduateprogram|\bph\.?d\b|postdoc|trainee\s+program|\binternship|\bintern\b|"
    r"praktikant|praktikophold|\bpraktik\b|bachelorprojekt|speciale|thesis|"
    r"student\s+(?:recruit|lead|engagement|advisor|counsel)|studievejled",
    re.I,
)

DK_PLACES = [
    "denmark", "danmark", "dänemark", "copenhagen", "københavn", "kobenhavn",
    "aarhus", "århus", "odense", "aalborg", "billund", "bagsværd", "bagsvaerd",
    "måløv", "maaloev", "kalundborg", "hillerød", "hillerod", "lyngby", "ballerup",
    "hellerup", "gentofte", "søborg", "soborg", "valby", "frederiksberg",
    "brabrand", "skejby", "silkeborg", "vejle", "kolding", "esbjerg", "horsens",
    "randers", "herning", "struer", "lemvig", "fredericia", "roskilde", "køge",
    "kastrup", "taastrup", "høje taastrup", "glostrup", "brøndby", "herlev",
    "ringsted", "næstved", "holstebro", "viby", "risskov", "tilst", "skanderborg",
    "hørsholm", "kgs. lyngby", "kongens lyngby", ", dk", " dk-", "dk ",
]


CPH_PLACES = [
    "københavn", "kobenhavn", "copenhagen", "frederiksberg", "storkøbenhavn", "hovedstad", "gentofte", "hellerup",
    "lyngby", "søborg", "soborg", "valby", "glostrup", "ballerup", "herlev", "brøndby", "hvidovre", "rødovre",
    "albertslund", "taastrup", "kastrup", "tårnby", "ørestad", "nordhavn", "bagsværd", "måløv", "hørsholm",
    "gladsaxe", "virum", "holte", "birkerød", "farum", "værløse", "skovlunde", "ishøj", "vallensbæk", "greve",
    "dragør", "hillerød", "roskilde", "kongens lyngby", "charlottenlund", "klampenborg", "nærum", "kgs. lyngby",
    "remote", "hybrid", "hjemmefra",
]


NON_CPH = ["aarhus", "århus", "odense", "aalborg", "esbjerg", "vejle", "kolding", "horsens", "herning", "silkeborg",
           "randers", "holbæk", "næstved", "billund", "fredericia", "viborg", "sønderborg", "svendborg", "slagelse", "holstebro"]


def is_cph(loc: str | None, title: str = "") -> bool:
    """Storkøbenhavn (+ remote). Ukendt/landsdækkende lokation tæller med, medmindre titlen nævner en anden by."""
    t = (loc or "").lower().strip()
    if any(p in t for p in CPH_PLACES):
        return True
    if not t or t in ("danmark", "denmark"):
        tl = (title or "").lower()
        return not any(c in tl for c in NON_CPH) or any(p in tl for p in CPH_PLACES)
    return False


def is_denmark(*texts: str | None) -> bool:
    t = " ".join(x or "" for x in texts).lower()
    return any(p in t for p in DK_PLACES)


STUDENT_BODY_RE = re.compile(
    r"studentermedhj|studentermedarb|student\s+assistant|student\s+worker|studiejob|working\s+student|"
    r"ved\s+siden\s+af\s+(?:dit|dine)\s+studi|alongside\s+your\s+stud|"
    r"\b(?:1[0-9]|20)\s*[-–]\s*(?:1[0-9]|2[0-5])\s+(?:timer|hours)\s+(?:om|per|a|pr\.?)\s+(?:ugen|week)",
    re.I,
)


def is_student_body(text: str) -> bool:
    """Studenterjob hvor titlen ikke siger det, men opslagsteksten gør."""
    return bool(STUDENT_BODY_RE.search(text or "")) and not EXCLUDE_RE.search((text or "")[:400])


# --- Udvidet filter: studiejob uden ordet "student" -------------------------------------------
# Stærke tegn: teksten taler direkte om at kombinere jobbet med studier
STUDY_SIGNAL_RE = re.compile(
    r"ved\s+siden\s+af\s+(?:dit|dine|studiet|studierne|din\s+uddannelse)|sideløbende\s+med\s+(?:dit|dine|din)\s+(?:studie|uddannelse)|"
    r"kombiner\w*\s+med\s+(?:dine\s+|dit\s+)?(?:studier|studiet|studie|uddannelse)|combin\w*\s+with\s+(?:your\s+)?stud|"
    r"alongside\s+your\s+(?:studies|degree|education)|while\s+(?:you\s+are\s+)?(?:studying|completing\s+your)|"
    r"(?:du|you)\s+(?:er|are)\s+(?:i\s+gang\s+med|currently\s+(?:enrolled|studying|pursuing))|"
    r"igangværende\s+(?:videregående\s+)?uddannelse|currently\s+enrolled|"
    r"(?:fleksib|hensyn)[^.]{0,60}(?:eksamen|eksamens|exam)",
    re.I,
)
# Svage tegn: nævner studerende/studentermedhjælpere – tæller kun sammen med deltid/≤25 timer
WEAK_STUDY_RE = re.compile(
    r"studentermedhj|studentermedarb|student\s+assistant|student\s+worker|studiejob|working\s+student|studerende",
    re.I,
)
_HOURS_RE = re.compile(r"\b(\d{1,2})\s*(?:[-–]\s*(\d{1,2})\s*)?(?:timer|t\.|hours?|hrs)\s*(?:om|per|pr\.?|a|i|/)\s*(?:ugen|uge|week|wk)", re.I)
PARTTIME_RE = re.compile(r"\bdeltid|part[- ]time|deltidsstilling|deltidsjob", re.I)
SENIOR_RE = re.compile(r"chef\b|\bsenior|\blead\b|leder\b|\bchef\b|\bhead\b|director|direktør|\bmanager\b|erfaren|experienced|principal|\bpartner\b|\bVP\b", re.I)


def study_hours(text: str) -> bool:
    """Timetal, der passer til et studiejob (højst 25 t/uge)."""
    for m in _HOURS_RE.finditer(text or ""):
        hi = int(m.group(2) or m.group(1))
        if 5 <= hi <= 25:
            return True
    return False


def student_fit(title: str, text: str = "") -> str | None:
    """Hvor sikkert er det et studiejob?
    'sikker'     – titlen siger student/studiejob
    'sandsynlig' – teksten taler om studier ved siden af jobbet, studentermedhjælper e.l.
    'mulig'      – deltid/≤25 timer om ugen og ikke en senior-/lederstilling
    None         – ingen tegn på studiejob (eller praktik/graduate/ph.d.)
    """
    if EXCLUDE_RE.search(title or ""):
        return None
    if is_student(title):
        return "sikker"
    if SENIOR_RE.search(title or ""):
        return None
    body = (text or "")[:8000]
    parttime = bool(PARTTIME_RE.search(title or "") or study_hours(title + " " + body) or PARTTIME_RE.search(body[:1500]))
    if STUDY_SIGNAL_RE.search(body) or (parttime and WEAK_STUDY_RE.search(body)):
        return "sandsynlig"
    if parttime:
        return "mulig"
    return None


def is_student(title: str) -> bool:
    return bool(STUDENT_RE.search(title or "")) and not EXCLUDE_RE.search(title or "")


TOPICS = {
    "Data & analyse": r"data\s*anal|dataanal|datahåndtering|datamodel|dataflow|data\s+&\s+ai|analytics|analyt|business intelligence|\bbi\b|dashboards?",
    "SQL": r"\bsql\b|t-sql|postgres|snowflake|bigquery|databricks",
    "Automatisering": r"automati|\brpa\b|power automate|snaplogic|integration|workflow",
    "AI": r"\bai\b|kunstig intelligens|artificial intelligence|machine learning|\bml\b|genai|llm|ai-agent|copilot",
    "Proces": r"procesoptim|procesudvikl|procesforbedr|process excellence|process improvement|process optimi|continuous improvement|\\blean\\b|optimering|optimi[sz]ation|operations research",
    "Digitalisering": r"digitali|it[- ]udvikling|it development|requirements|kravindsamling|kravspec|validering|kvalitetssikring",
    "Portfolio & investering": r"porteføl|portfolio management|portfolio analy|asset management|kapitalforvaltning|investment (?:management|analy|team|banking)|investering|fixed income|equities|trading|pension fund",
    "Finans": r"business finance|finance|finans|risk|risiko|controlling|controller|treasury|økonomi|accounting|regnskab|valuation",
    "Consulting": r"consulting|consultant|advisory|management consult|(?<!salgs)(?<!kunde)(?<!personale)(?<!service)(?<!butiks)konsulent",
    "Power BI / Excel": r"power\s*bi|power query|excel|vba",
    "Python": r"python|pandas",
}
_TOPIC_RE = {k: re.compile(v, re.I) for k, v in TOPICS.items()}


def topic_tags(*texts: str) -> list[str]:
    t = " ".join(texts)
    return [k for k, rx in _TOPIC_RE.items() if rx.search(t)]


DEADLINE_RES = [
    re.compile(r"(?:ansøgningsfrist|frist|senest|deadline|apply by|application deadline)[^\n]{0,40}?"
               r"(\d{1,2})\.?\s*(januar|februar|marts|april|maj|juni|juli|august|september|oktober|november|december|"
               r"jan|feb|mar|apr|may|jun|jul|aug|sep|oct|okt|nov|dec)[a-z]*\.?\s*(\d{4})?", re.I),
    re.compile(r"(?:ansøgningsfrist|frist|senest|deadline|apply by|application deadline)[^\n]{0,40}?"
               r"(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})", re.I),
]
_MONTHS = {m: i for i, ms in enumerate([
    ("januar", "jan"), ("februar", "feb"), ("marts", "mar", "march"), ("april", "apr"), ("maj", "may"),
    ("juni", "jun", "june"), ("juli", "jul", "july"), ("august", "aug"), ("september", "sep"),
    ("oktober", "okt", "oct", "october"), ("november", "nov"), ("december", "dec")], start=1) for m in ms}


def find_deadline(text: str, today_year: int) -> Optional[str]:
    """Finder ansøgningsfrist i teksten og returnerer ISO-dato. Deterministisk, ikke AI."""
    if not text:
        return None
    m = DEADLINE_RES[0].search(text)
    if m:
        d, mon, y = m.group(1), m.group(2).lower(), m.group(3)
        mo = _MONTHS.get(mon) or _MONTHS.get(mon[:3])
        if mo:
            try:
                return f"{int(y) if y else today_year:04d}-{mo:02d}-{int(d):02d}"
            except ValueError:
                pass
    m = DEADLINE_RES[1].search(text)
    if m:
        d, mo, y = (int(x) for x in m.groups())
        if y < 100:
            y += 2000
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{mo:02d}-{d:02d}"
    return None


# ---------------------------------------------------------------- model
@dataclass
class Job:
    company: str
    title: str
    url: str                      # opslaget
    apply_url: str = ""           # ansøgningslink (hvis kendt, ellers = url)
    location: str = ""
    posted: str = ""              # ISO dato hvis kendt
    deadline: str = ""            # ISO dato hvis fundet
    description_md: str = ""
    source: str = ""
    external_id: str = ""
    tags: list[str] = field(default_factory=list)
    top50: bool = True            # False = virksomhed uden for top 50 (kun fra Jobindex)
    fit: str = "sikker"           # sikker | sandsynlig | mulig (se student_fit)

    @property
    def id(self) -> str:
        key = f"{self.company}|{self.external_id or self.url}".lower()
        return hashlib.sha1(key.encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["id"] = self.id
        if not d["apply_url"]:
            d["apply_url"] = self.url
        return d


def jsonld_jobposting(html: str) -> dict | None:
    """Mange karrieresider har schema.org JobPosting til Google Jobs."""
    s = soup(html)
    for tag in s.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or tag.text or "")
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for it in list(items):
            if isinstance(it, dict) and "@graph" in it:
                items.extend(it["@graph"])
        for it in items:
            if isinstance(it, dict) and "JobPosting" in str(it.get("@type")):
                return it
    return None


def jsonld_location(jp: dict) -> str:
    locs = jp.get("jobLocation") or []
    if isinstance(locs, dict):
        locs = [locs]
    out = []
    for l in locs:
        a = (l or {}).get("address") or {}
        if isinstance(a, dict):
            out.append(", ".join(clean(str(a.get(k, ""))) for k in ("addressLocality", "addressRegion", "addressCountry") if a.get(k)))
        elif isinstance(a, str):
            out.append(a)
    return " | ".join(o for o in out if o)

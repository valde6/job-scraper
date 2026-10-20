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
from markdownify import MarkdownConverter

_MD = MarkdownConverter(heading_style="ATX", strip=["img"])

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36 job-scraper (personal use)"
)

_session = requests.Session()
_session.headers.update({"User-Agent": UA, "Accept-Language": "da,en;q=0.8"})


# ---------------------------------------------------------------- optag / afspil HTTP
# SCRAPER_RECORD=<mappe>  gemmer alle svar (bruges til test-fixtures)
# SCRAPER_REPLAY=<mappe>  svarer fra gemte filer uden netværk (bruges i tests)
def _req_key(method: str, url: str, kw: dict) -> str:
    body = kw.get("json") if kw.get("json") is not None else kw.get("data")
    raw = json.dumps([method.upper(), url, sorted((kw.get("params") or {}).items()), body], sort_keys=True,
                     ensure_ascii=False, default=str)
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _fixture_dir(env: str):
    import os
    from pathlib import Path
    d = os.environ.get(env)
    return Path(d) if d else None


def _save_fixture(d, key: str, method: str, url: str, r: requests.Response) -> None:
    import gzip
    d.mkdir(parents=True, exist_ok=True)
    rec = {"method": method, "url": url, "final_url": r.url, "status": r.status_code,
           "content_type": r.headers.get("content-type", ""), "text": r.text}
    (d / f"{key}.json.gz").write_bytes(gzip.compress(json.dumps(rec, ensure_ascii=False).encode()))


def _load_fixture(d, key: str, method: str, url: str) -> requests.Response:
    import gzip
    f = d / f"{key}.json.gz"
    if not f.exists():
        raise requests.ConnectionError(f"REPLAY: intet gemt svar for {method} {url} ({key})")
    rec = json.loads(gzip.decompress(f.read_bytes()))
    r = requests.Response()
    r.status_code, r.url, r.encoding = rec["status"], rec.get("final_url") or url, "utf-8"
    r._content = rec["text"].encode("utf-8")
    r.headers["content-type"] = rec.get("content_type", "")
    return r


def _retry_wait(r: requests.Response, attempt: int) -> float:
    """Ventetid før næste forsøg. Ved 429 respekteres Retry-After (højst 30 s), ellers 2, 5, 8 … sekunder."""
    base = 2 + attempt * 3
    if r.status_code == 429:
        ra = (r.headers.get("Retry-After") or "").strip()
        if ra.isdigit():
            return min(max(int(ra), base), 30)
        return min(base * 2, 30)
    return base


def http(method: str, url: str, *, retries: int = 2, **kw) -> requests.Response:
    replay = _fixture_dir("SCRAPER_REPLAY")
    if replay:
        r = _load_fixture(replay, _req_key(method, url, kw), method, url)
        r.raise_for_status()
        return r
    record = _fixture_dir("SCRAPER_RECORD")
    key = _req_key(method, url, kw) if record else ""
    kw.setdefault("timeout", 25)
    last = None
    for attempt in range(retries + 1):
        try:
            r = _session.request(method, url, **kw)
            if r.status_code in (429, 502, 503, 504) and attempt < retries:
                time.sleep(_retry_wait(r, attempt))
                continue
            r.raise_for_status()
            if record:
                _save_fixture(record, key, method, url, r)
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
    """HTML → markdown. Parser = lxml: html.parser behandler <br> uden / som en beholder,
    og så smider markdownify resten af teksten væk (fundet via Mærsk-fixture)."""
    if not html:
        return ""
    html = re.sub(r"&#x[aA];|&#10;", "\n", html)
    s = BeautifulSoup(html, "lxml")
    for t in s(["script", "style", "noscript"]):
        t.decompose()
    md = _MD.convert_soup(s)
    md = re.sub(r"[ \t]+\n", "\n", md)
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
    r"studentmedhj|working\s+student|werkstudent|part[- ]time\s+student|"
    r"\bstud\.\s?(?:jur|merc|polit|scient|oecon|soc)\b|jurastuderende",     # 20/10: advokatfirmaernes "stud.jur."
    re.I,
)
# ting der ligner studenterjob men ikke er det
EXCLUDE_RE = re.compile(
    r"graduate\s+program|graduateprogram|\bph\.?d\b|postdoc|trainee\s+program|\binternship|\bintern\b|"
    r"praktikant|praktikophold|\bpraktik\b|bachelorprojekt|speciale|thesis|"
    r"student\s+(?:recruit|lead|engagement|advisor|counsel)|studievejled",
    re.I,
)

# ---------------------------------------------------------------- jobtyper (platform-kørslen)
# Den personlige kørsel vil kun have studiejob. Platform-kørslen (Jobradar) slår praktik og graduate til med
# set_job_types(), så adapterne også beholder dem. Jobtypen bestemmes bagefter med job_type().
# "intern" kun som engelsk navneord ("Intern - Finance", "Summer Intern"), ikke dansk tillægsord ("intern kontrol", "Intern sælger")
PRAKTIK_RE = re.compile(r"\binternship|\bintern\b(?=\s*(?:$|[-–(),|/:]|(?:for|in|at|to|with|within|på|hos|til|i)\b))|"
                        r"praktikant|praktikophold|\bpraktik\b|sommerpraktik|summer\s+intern", re.I)
# Afdelingsnavne som "Afd. for Uddannelse og Studerende" er ikke tegn på et studiejob
STUDENT_SERVICE_RE = re.compile(r"\b(?:for|og|and)\s+studerende\b|\bstudent\s+(?:services|affairs|centre|center)\b", re.I)
GRADUATE_RE = re.compile(r"\bgraduate|\btrainee|nyuddannet|young\s+professional", re.I)
HARD_EXCLUDE_RE = re.compile(
    r"\bph\.?d\b|postdoc|bachelorprojekt|speciale|thesis|"
    r"student\s+(?:recruit|lead|engagement|advisor|counsel)|studievejled|\bsenior\b|"
    r"laborant|lærling|\belev\b|kontorelev|elevplads|erhvervsuddannelse|apprentice|skolepraktik|"
    r"pensionerede|genansættelse",
    re.I,
)
# Arrangementer, der ligner job i rekrutteringssystemerne (fx "Graduate Dinner", "Student Event: …")
EVENT_RE = re.compile(
    r"\b(?:dinner|webinar|open\s+house|career\s+day|karrieredag|informationsmøde|info[- ]?(?:session|meeting|møde)|"
    r"networking|evening|night|meetup|bootcamp|hackathon|case\s+competition|workshop)\b|\bevent\b(?!s)|\barrangement\b",
    re.I,
)
# Butiks-, kantine- og servicejob (Coop, Bestseller, 7-Eleven …). Ofte deltid "for studerende", men ikke relevante
# studiejob for Studieradars målgruppe. Kun i platform-kørslen (job_type), 17/10.
RETAIL_RE = re.compile(
    r"salgsassistent|sales\s+(?:assistant|advisor|associate)|butiks?(?:assistent|medarbejder|ansat|elev)|"
    r"kassemedarbejder|kasse/kiosk|\bkiosk\b|ferskvare|lukkeansvarlig|servicemedarbejder|[ou]\w*\s+18\s+år|sabb?atår|"
    r"7-eleven|\bcashier|(?:store|retail)\s+(?:assistant|associate)|opfyldning|varepåfyld|lagermedarbejder|"
    r"rengøring|\bafløser|\bkok\b|\bcater|\btjener\b|opvask|chauffør|pakkemedarbejder|ufaglært",
    re.I,
)
_EXTRA_TYPES: set[str] = set()


def set_job_types(types) -> None:
    """Fx set_job_types({"studiejob", "praktik", "graduate"}). Påvirker student_fit/is_student i hele processen."""
    global _EXTRA_TYPES
    _EXTRA_TYPES = set(types) - {"studiejob"}


def _extra_type_ok(title: str) -> bool:
    if not _EXTRA_TYPES or not title or HARD_EXCLUDE_RE.search(title):
        return False
    return bool(("praktik" in _EXTRA_TYPES and PRAKTIK_RE.search(title))
                or ("graduate" in _EXTRA_TYPES and GRADUATE_RE.search(title)))


def job_type(title: str, text: str = "") -> str | None:
    """studiejob | praktik | graduate | None. Titlen afgør praktik/graduate; ellers studiejob via student_fit."""
    t = title or ""
    if HARD_EXCLUDE_RE.search(t) or EVENT_RE.search(t) or RETAIL_RE.search(t):
        return None
    if PRAKTIK_RE.search(t):
        return "praktik"
    if GRADUATE_RE.search(t):
        return "graduate"
    t2 = STUDENT_SERVICE_RE.sub(" ", t)
    if t2 != t and not STUDENT_RE.search(t2):
        return None
    return "studiejob" if student_fit(t2, text) else None


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


# Sjælland (inkl. Storkøbenhavn) til platform-kørslen
SJ_PLACES = [
    "køge", "koge", "ringsted", "slagelse", "næstved", "naestved", "holbæk", "holbaek", "kalundborg", "sorø", "soro",
    "helsingør", "helsingor", "fredensborg", "humlebæk", "humlebaek", "allerød", "allerod", "frederikssund",
    "frederiksværk", "hundested", "gilleleje", "solrød", "solrod", "stenløse", "stenlose", "smørum", "smorum",
    "vordingborg", "faxe", "haslev", "lejre", "stevns", "odsherred", "nykøbing sj", "rungsted", "kokkedal", "nivå",
    "zealand", "sjælland", "sjaelland", "region hovedstaden", "capital region", "bornholm", "rønne",
]
NON_SJ = ["aarhus", "århus", "odense", "aalborg", "esbjerg", "vejle", "kolding", "horsens", "herning", "silkeborg",
          "randers", "billund", "fredericia", "viborg", "sønderborg", "svendborg", "holstebro", "skive", "struer",
          "aabenraa", "haderslev", "thisted", "hjørring", "frederikshavn", "middelfart", "nyborg", "nordborg",
          "skanderborg", "grenaa", "ikast", "brande", "varde", "ribe", "tønder", "jylland", "fyn", "jutland", "funen",
          "region syddanmark", "region midtjylland", "region nordjylland", "southern denmark", "central denmark",
          "north denmark", "færøerne", "grønland", "nuuk", "tórshavn",
          # 18/10: byer, der gav "ukendt" i stedet for "uden for Sjælland" (Eurofins, Orkla, Matas)
          "aabybro", "vejen", "søndersø", "padborg", "grindsted", "give", "hobro", "hadsund", "hedensted", "tarm",
          "ringkøbing", "lemvig", "struer", "thisted", "nykøbing mors", "brønderslev", "sæby", "skagen", "løgstør",
          "kjellerup", "bjerringbro", "hammel", "odder", "ebeltoft", "rønde", "kalø", "galten", "hinnerup", "lystrup",
          "vojens", "gram", "rødding", "kolding", "bramming", "ølgod", "fåborg", "faaborg", "assens", "bogense",
          "kerteminde", "nyborg", "ringe", "glamsbjerg", "otterup", "munkebo", "langeland", "ærø", "tranbjerg",
          "egå", "åbyhøj", "hasselager", "skødstrup", "sabro", "hørning", "låsby", "vamdrup", "lunderskov",
          "sønderjylland", "nordjylland", "vestjylland", "østjylland", "midtjylland", "sydjylland", "sydfyn", "nordfyn",
          "vestfyn", "østfyn"]
_POSTCODE_RE = re.compile(r"\b(?:dk-?)?([1-9]\d{3})\s+[A-ZÆØÅa-zæøå]")


def _postcode_region(t: str) -> str | None:
    """Danske postnumre: 1000-2999 Storkøbenhavn, 3000-4999 resten af Sjælland/øerne, 5000+ Fyn og Jylland."""
    m = _POSTCODE_RE.search(t)
    if not m:
        return None
    n = int(m.group(1))
    return "storkbh" if n < 3000 else "sjaelland" if n < 5000 else "udenfor"


def region(loc: str | None, title: str = "") -> str | None:
    """'storkbh' | 'sjaelland' | 'ukendt' (fx bare "Danmark") | None (uden for Sjælland)."""
    t = f"{loc or ''}".lower().replace("new zealand", "nz")   # "zealand" = Sjælland, men ikke New Zealand
    if any(p in t for p in CPH_PLACES):
        return "storkbh"
    if any(p in t for p in SJ_PLACES):
        return "sjaelland"
    tl = (title or "").lower()
    if any(re.search(rf"\b{re.escape(p)}\b", t) for p in NON_SJ) or any(re.search(rf"\b{re.escape(p)}\b", tl) for p in NON_SJ):
        return None
    pc = _postcode_region(loc or "")
    if pc == "udenfor":
        return None
    return pc or "ukendt"


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
    r"\b(?:du|you)\s+(?:læser|studerer|study|are\s+studying)\s+(?:på\s+|en\s+|til\s+|a\s+)?(?:relevant\s+)?"
    r"(?:bachelor|kandidat|cand\.|ha\b|hd\b|universit|videregående|master)|"
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
    if _extra_type_ok(title):
        return "sikker"
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
    if _extra_type_ok(title):
        return True
    return bool(STUDENT_RE.search(title or "")) and not EXCLUDE_RE.search(title or "")


TOPICS = {
    "Data & analyse": r"data\s*anal|dataanal|datahåndtering|datamodel|dataflow|data\s+&\s+ai|analytics|analyt|business intelligence|\bbi\b|dashboards?",
    "SQL": r"\bsql\b|t-sql|postgres|snowflake|bigquery|databricks",
    "Automatisering": r"automati|\brpa\b|power automate|snaplogic|integration|workflow",
    "AI": r"\bai\b|kunstig intelligens|artificial intelligence|machine learning|\bml\b|genai|llm|ai-agent|copilot",
    "Proces": r"procesoptim|procesudvikl|procesforbedr|process excellence|process improvement|process optimi|continuous improvement|\blean\b|optimering|optimi[sz]ation|operations research",
    "Digitalisering": r"digitali|it[- ]udvikling|it development|requirements|kravindsamling|kravspec|validering|kvalitetssikring",
    "Portfolio & investering": r"porteføl|portfolio management|portfolio analy|asset management|kapitalforvaltning|investment (?:management|analy|team|banking)|investering|fixed income|equities|trading|pension fund",
    "Finans": r"business finance|finance|finans|risk|risiko|controlling|controller|treasury|økonomi|accounting|regnskab|valuation",
    "Consulting": r"consulting|consultant|advisory|management consult|(?<!salgs)(?<!kunde)(?<!personale)(?<!service)(?<!butiks)konsulent",
    "Power BI / Excel": r"power\s*bi|power query|excel|vba",
    "Python": r"python|pandas",
}
_TOPIC_RE = {k: re.compile(v, re.I) for k, v in TOPICS.items()}


def set_topics(topics: dict[str, str]) -> None:
    """Skift emne-ordbogen (platform-kørslen bruger den brede nøgleordsordbog for alle studieretninger)."""
    global _TOPIC_RE
    _TOPIC_RE = {k: re.compile(v, re.I) for k, v in topics.items()}


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
            data = json.loads(tag.string or tag.text or "", strict=False)   # nogle sider har linjeskift i strenge
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


# ---------------------------------------------------------------- strukturerede jobdata (robust, uafhængig af layout)
_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
_MONTH_ABBR = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}


def _iso_date(v) -> str:
    """'2026-10-14', '2026-10-14T00:00Z' eller SuccessFactors' 'Mon Oct 12 00:00:00 UTC 2026' → '2026-10-12'."""
    t = str(v or "")
    m = _DATE_RE.search(t)
    if m:
        return m.group(1)
    m = re.search(r"\b([A-Z][a-z]{2})\s+(\d{1,2})\b.*?\b(\d{4})\b", t)
    if m and m.group(1).lower() in _MONTH_ABBR:
        return f"{m.group(3)}-{_MONTH_ABBR[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"
    return ""


def _microdata(s: BeautifulSoup) -> dict | None:
    scope = s.find(attrs={"itemtype": re.compile(r"schema\.org/JobPosting", re.I)})
    if not scope:
        return None
    def prop(name):
        el = scope.find(attrs={"itemprop": name})
        if not el:
            return ""
        return el.get("content") if el.get("content") is not None else (el.decode_contents() if name == "description" else el.get_text(" "))
    loc_bits = [el.get("content") or el.get_text(" ") for el in scope.select(
        "[itemprop=jobLocation] [itemprop=streetAddress], [itemprop=jobLocation] [itemprop=addressLocality], "
        "[itemprop=jobLocation] [itemprop=addressRegion], [itemprop=jobLocation] [itemprop=addressCountry]")]
    return {"title": clean(prop("title")), "description_html": prop("description") or "",
            "location": clean(", ".join(b for b in loc_bits if clean(b))),
            "posted": _iso_date(prop("datePosted")), "deadline": _iso_date(prop("validThrough"))}


def _label_fields(s: BeautifulSoup) -> dict:
    """Felter vist som 'etiket: værdi' (fx Avature: article__content__view__field). Matcher på klassenavne, der indeholder
    'label'/'value', så små layoutændringer ikke ødelægger noget."""
    out, free = {}, []
    for box in s.find_all(class_=re.compile(r"(?:^|_)field$|__field\b|\bfield\b")):
        lab = box.find(class_=re.compile(r"label", re.I))
        val = box.find(class_=re.compile(r"value", re.I))
        if not val:
            continue
        if lab:
            out[clean(lab.get_text(" ")).lower()] = val
        else:
            free.append(val)
    if free:
        out["_description"] = max(free, key=lambda v: len(v.get_text(" ")))
    return out


def extract_posting(html: str) -> dict:
    """Ét jobopslag → {title, description_html, location, posted, deadline}.

    Rækkefølge: schema.org JSON-LD → schema.org microdata → etiket/værdi-felter → <h1>/og:title + sidens hovedtekst.
    JSON-LD og microdata findes for at Google for Jobs kan læse opslaget, så de ændres sjældent – i modsætning til layoutet.
    Felter, der mangler i én kilde, udfyldes fra den næste."""
    s = soup(html)
    res = {"title": "", "description_html": "", "location": "", "posted": "", "deadline": ""}

    def fill(d):
        for k, v in (d or {}).items():
            if v and not res.get(k):
                res[k] = v

    jp = jsonld_jobposting(html)
    if jp:
        fill({"title": clean(jp.get("title")), "description_html": jp.get("description") or "",
              "location": jsonld_location(jp), "posted": _iso_date(jp.get("datePosted")),
              "deadline": _iso_date(jp.get("validThrough"))})
    fill(_microdata(s))
    f = _label_fields(s)
    if f:
        def fv(*names):
            for n in names:
                for k, v in f.items():
                    if k.startswith(n):
                        return clean(v.get_text(" "))
            return ""
        fill({"title": fv("job title", "stillingsbetegnelse", "titel"),
              "location": fv("location", "lokation", "arbejdssted", "sted"),
              "description_html": f["_description"].decode_contents() if "_description" in f else "",
              "deadline": _iso_date(fv("application deadline", "ansøgningsfrist", "deadline"))})
        etype = fv("employment type", "ansættelsestype", "stillingstype")
        if etype:
            res["employment_type"] = etype
    og = s.find("meta", attrs={"property": "og:title"})
    h1 = s.find("h1")
    fill({"title": clean((og or {}).get("content") if og else "") or clean(h1.get_text(" ") if h1 else "")})
    if not res["description_html"]:
        main = s.find("main") or s.find("article") or s.body
        if main:
            for t in main.find_all(["script", "style", "nav", "header", "footer", "form"]):
                t.decompose()
            res["description_html"] = main.decode_contents()
    return res


# ---------------------------------------------------------------- frasorterede opslag (til fejlfinding af filtrene)
REJECTED: list[dict] = []


def reject(company: str, title: str, reason: str, url: str = "") -> None:
    """Notér et opslag, som en adapter så men valgte fra. Skrives til data/jobradar/rejected.json efter kørslen,
    så vi kan se, om filtrene smider rigtige studiejob væk (fx 'ikke studiejob', 'uden for Danmark')."""
    if len(REJECTED) < 5000:
        REJECTED.append({"company": company, "title": clean(title)[:160], "reason": reason, "url": url})


# ---------------------------------------------------------------- robots.txt
_ROBOTS: dict[str, object] = {}


def robots_allows(url: str) -> bool:
    """Respektér robots.txt (regel 6 i AGENTS.md). Kan robots.txt ikke hentes, er alt tilladt (standard)."""
    from urllib.parse import urlparse
    from urllib.robotparser import RobotFileParser
    u = urlparse(url)
    base = f"{u.scheme}://{u.netloc}"
    rp = _ROBOTS.get(base)
    if rp is None:
        rp = RobotFileParser()
        try:
            rp.parse(get(base + "/robots.txt", retries=0).text.splitlines())
        except Exception:  # noqa: BLE001
            rp.parse([])
        _ROBOTS[base] = rp
    return rp.can_fetch("*", url)  # type: ignore[attr-defined]


def robots_sitemaps(base: str) -> list[str]:
    try:
        txt = get(base.rstrip("/") + "/robots.txt", retries=0).text
    except Exception:  # noqa: BLE001
        return []
    return re.findall(r"(?im)^\s*sitemap:\s*(\S+)", txt)

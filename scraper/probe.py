"""Udviklingsværktøj. Hver linje i probe.txt:
    GET <url>
    POST <url> <json-body>
    SCRAPE <virksomhedsnavn>        (kører adapteren fra companies.yaml og gemmer resultatet)
Svar gemmes i data/probe/NN.txt (status, headers, første 60 kB)."""
import json, re, shutil, traceback
from urllib.parse import urljoin
from .common import soup, clean

SECRET_RE = re.compile(r"(AIza[0-9A-Za-z_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_\w+|sk-[A-Za-z0-9]{20,}|xox[abp]-[\w-]+|"
                       r"eyJ[\w-]{10,}\.[\w-]{10,}\.[\w-]{5,}|(?<![A-Za-z0-9/])[A-Za-z0-9+/_-]{40,}={0,2})")


def redact(t):
    return SECRET_RE.sub("[REDACTED]", t)


def shrink(o, depth=0):
    if isinstance(o, dict):
        return {k: shrink(v, depth + 1) for k, v in list(o.items())[:40]}
    if isinstance(o, list):
        return [shrink(v, depth + 1) for v in o[:6]] + ([f"... +{len(o)-6}"] if len(o) > 6 else [])
    if isinstance(o, str):
        return o[:300]
    return o


def summarize(r):
    ct = r.headers.get("content-type", "")
    t = r.text
    try:
        return "JSON\n" + json.dumps(shrink(r.json()), ensure_ascii=False, indent=1)[:25000]
    except Exception:
        pass
    s = soup(t)
    out = [f"TYPE {ct}", f"TITLE {clean(s.title.get_text()) if s.title else ''}"]
    if "<rss" in t[:500] or "<item>" in t:
        items = s.find_all("item")
        out.append(f"RSS items={len(items)}")
        for it in items[:4]:
            out.append("ITEM " + str(it)[:1500])
    links = []
    for a in s.find_all("a", href=True):
        txt = clean(a.get_text())
        if txt and len(txt) > 3:
            links.append(f"{txt[:90]} -> {urljoin(r.url, a['href'])[:200]}")
    out.append(f"LINKS {len(links)}")
    out += links[:120]
    out.append("SCRIPTS " + " | ".join(x['src'][:120] for x in s.find_all('script', src=True))[:3000])
    ld = [x.string[:1500] for x in s.find_all("script", type="application/ld+json") if x.string]
    out.append(f"JSONLD {len(ld)}")
    out += ld[:2]
    m = re.search(r"phApp\.ddo\s*=\s*(\{.{0,3000})", t, re.S)
    if m:
        out.append("PHENOM_DDO " + m.group(1)[:3000])
    out.append("TEXT " + clean(s.get_text(" "))[:4000])
    return "\n".join(out)

from pathlib import Path
import yaml
from .common import http
from .adapters import ADAPTERS

ROOT = Path(__file__).resolve().parent.parent
out = ROOT / "data" / "probe"
shutil.rmtree(out, ignore_errors=True)
out.mkdir(parents=True)
lines = [l.strip() for l in (ROOT / "probe.txt").read_text().splitlines() if l.strip() and not l.startswith("#")]
companies = {c["name"]: c for c in yaml.safe_load((ROOT / "companies.yaml").read_text())["companies"]}
summary = []
for i, line in enumerate(lines, 1):
    f = out / f"{i:02d}.txt"
    try:
        parts = line.split(" ", 2)
        if parts[0] == "SCRAPE":
            c = companies[line[7:].strip()]
            listed, jobs = ADAPTERS[c["source"]["type"]]({**c["source"], "name": c["name"]})
            body = json.dumps({"listed": listed, "jobs": [j.to_dict() for j in jobs]}, ensure_ascii=False, indent=1)
            f.write_text(redact(f"{line}\nOK listed={listed} matched={len(jobs)}\n\n{body[:40000]}"))
            summary.append(f"{i:02d} OK listed={listed} matched={len(jobs)} | {line}")
            continue
        if parts[0] == "RAW":
            r = http("GET", parts[1], retries=0, timeout=25)
            f.write_text(redact(f"{line}\nSTATUS {r.status_code}\n\n{r.text[:int(parts[2]) if len(parts) > 2 else 12000]}"))
            summary.append(f"{i:02d} RAW {r.status_code} {len(r.text)}B | {line}")
            continue
        kw = {"retries": 0, "timeout": 25}
        if parts[0] == "POST":
            kw["json"] = json.loads(parts[2]) if len(parts) > 2 else {}
        r = http(parts[0], parts[1], **kw)
        f.write_text(redact(f"{line}\nSTATUS {r.status_code} FINAL {r.url}\n\n{summarize(r)}"))
        summary.append(f"{i:02d} {r.status_code} {len(r.text)}B | {line}")
    except Exception as e:
        resp = getattr(e, "response", None)
        txt = redact(resp.text[:2000]) if resp is not None else ""
        f.write_text(f"{line}\nERROR {type(e).__name__}: {e}\n{traceback.format_exc()}\n{txt}")
        summary.append(f"{i:02d} ERR {type(e).__name__}: {str(e)[:120]} | {line}")
(out / "SUMMARY.txt").write_text("\n".join(summary))
print("\n".join(summary))

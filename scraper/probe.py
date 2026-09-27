"""Udviklingsværktøj. Hver linje i probe.txt:
    GET <url>
    POST <url> <json-body>
    SCRAPE <virksomhedsnavn>        (kører adapteren fra companies.yaml og gemmer resultatet)
Svar gemmes i data/probe/NN.txt (status, headers, første 60 kB)."""
import json, re, shutil, traceback
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
            f.write_text(f"{line}\nOK listed={listed} matched={len(jobs)}\n\n{body[:60000]}")
            summary.append(f"{i:02d} OK listed={listed} matched={len(jobs)} | {line}")
            continue
        kw = {"retries": 0, "timeout": 25}
        if parts[0] == "POST":
            kw["json"] = json.loads(parts[2]) if len(parts) > 2 else {}
        r = http(parts[0], parts[1], **kw)
        f.write_text(f"{line}\nSTATUS {r.status_code} FINAL {r.url}\n{dict(r.headers)}\n\n{r.text[:60000]}")
        summary.append(f"{i:02d} {r.status_code} {len(r.text)}B | {line}")
    except Exception as e:
        resp = getattr(e, "response", None)
        txt = resp.text[:3000] if resp is not None else ""
        f.write_text(f"{line}\nERROR {type(e).__name__}: {e}\n{traceback.format_exc()}\n{txt}")
        summary.append(f"{i:02d} ERR {type(e).__name__}: {str(e)[:120]} | {line}")
(out / "SUMMARY.txt").write_text("\n".join(summary))
print("\n".join(summary))

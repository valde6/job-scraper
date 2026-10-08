"""Tjek af Statens Rekrutteringsløsning (HR-Manager) og Emply-lister."""
import json, re
from collections import Counter
from ..common import get, student_fit, html_to_md, clean
from ..adapters.hrmanager import _title


def main():
    d = get("https://api.hr-manager.net/jobportal.svc/statensrekrutteringsloesning_tr/positionlist/json/",
            params={"incads": 1}).json()
    items = d.get("Items") or []
    print("stillinger i alt:", len(items))
    print("felter:", sorted(items[0].keys()))
    strkeys = {k: v for k, v in items[0].items() if isinstance(v, (str, int)) and v}
    print("eksempel:", json.dumps(strkeys, ensure_ascii=False)[:1500])
    for k in ("Department", "DepartmentName", "Company", "Employer", "OrganizationName"):
        if k in items[0]:
            print(k, "->", str(items[0][k])[:300])
    fits = Counter()
    for p in items:
        t = clean(_title(p))
        c = html_to_md(((p.get("Advertisements") or [{}])[0]).get("Content", ""))
        f = student_fit(t, c)
        fits[f] += 1
        if f:
            dep = p.get("Department") or {}
            print("STUDIE", f, "|", t[:80], "|", (dep.get("Name") if isinstance(dep, dict) else dep))
    print(fits)
    for t in ("aeldresagen", "kp"):
        h = get(f"https://{t}.career.emply.com/ledige-stillinger").text
        print(t, "ad-links:", len(set(re.findall(r"/ad/[\w-]+/\w{6}", h))), "api:", sorted(set(re.findall(r"/api/[\w/-]{3,60}", h)))[:15])

"""Oracle Recruiting Cloud (…oraclecloud.com/hcmUI/CandidateExperience/…/sites/CX_1).

Config: host: https://xxxx.fa.em2.oraclecloud.com   site: CX_1
"""
from ..common import Job, get, html_to_md, is_denmark, is_student, clean


def scrape(cfg):
    host, site = cfg["host"].rstrip("/"), cfg["site"]
    listed, jobs = 0, []
    for kw in ("student", "studentermedhjælper"):
        r = get(f"{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions", params={
            "onlyData": "true", "expand": "requisitionList",
            "finder": f'findReqs;siteNumber={site},keyword="{kw}",limit=200,sortBy=POSTING_DATES_DESC'}).json()
        for block in r.get("items", []):
            for p in block.get("requisitionList", []):
                listed += 1
                title = clean(p.get("Title"))
                loc = " | ".join([p.get("PrimaryLocation") or ""] + [x.get("Name", "") for x in p.get("secondaryLocations") or []])
                if not (is_student(title) and is_denmark(loc, p.get("PrimaryLocationCountry"))):
                    continue
                if any(j.external_id == str(p["Id"]) for j in jobs):
                    continue
                d = get(f"{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails", params={
                    "expand": "all", "onlyData": "true", "finder": f'ById;Id="{p["Id"]}",siteNumber={site}'}).json()
                it = (d.get("items") or [{}])[0]
                desc = "\n\n".join(html_to_md(it.get(k)) for k in ("ExternalDescriptionStr", "ExternalResponsibilitiesStr", "ExternalQualificationsStr"))
                url = f"{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{p['Id']}"
                jobs.append(Job(company=cfg["name"], title=title, url=url, apply_url=url + "/apply",
                                location=loc, posted=p.get("PostedDate", ""), description_md=desc,
                                source="oracle", external_id=str(p["Id"])))
    return listed, jobs

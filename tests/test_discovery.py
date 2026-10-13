"""Genkendelse af rekrutteringssystemer ud fra links i opslag (firma-niveau-opdagelse)."""
import pytest

from scraper.discover_jobindex import recognize, known_keys, company_from_title


@pytest.mark.parametrize("url,typ,key", [
    ("https://aeldresagen.career.emply.com/ad/studentermedarbejder/z9aebv", "emply", "emply:aeldresagen"),
    ("https://candidate.hr-manager.net/ApplicationInit.aspx?cid=1518&ProjectId=216584&DepartmentId=23763", "hrmanager", "hrmanager-cid:1518"),
    ("https://danskindustri.teamtailor.com/jobs/8501409-pa-konsulent?promotion=2230409-jobindex", "teamtailor", "teamtailor:danskindustri.teamtailor.com"),
    ("https://karriere.danskespil.dk/jobs/8512771-studentermedhjaelper-til-crm?promotion=2234893-jobindex", "teamtailor", "teamtailor:karriere.danskespil.dk"),
    ("https://svitzer.wd3.myworkdayjobs.com/da-DK/Svitzer_Careers/job/Copenhagen/Student-Assistant_R1", "workday", "workday:svitzer.wd3.myworkdayjobs.com/svitzer_careers"),
    ("https://efzu.fa.em2.oraclecloud.com/hcmUI/CandidateExperience/da/sites/CX_1/job/8370", "oracle", "oracle:efzu.fa.em2.oraclecloud.com"),
    ("https://jobs.smartrecruiters.com/Ramboll3/744000153497080-praktikant", "smartrecruiters", "smartrecruiters:ramboll3"),
    ("https://eyglobal.yello.co/jobs/-c3pdhRbykXkBsX0HXY2Zg?job_board_id=c1riT--B2O-KySgYWsZO1Q", "yello", "yello:c1riT--B2O-KySgYWsZO1Q"),
])
def test_recognize(url, typ, key):
    r = recognize(url)
    assert r and r[0] == typ and r[2] == key


@pytest.mark.parametrize("url", ["https://www.lsb.dk/", "https://www.beumergroup.com/jobs-career/", "https://www.ey.com/da_dk/careers"])
def test_not_recognized(url):
    assert recognize(url) is None


def test_known_keys_prevent_duplicates():
    emps = [{"name": "Svitzer", "source": {"type": "workday", "url": "https://svitzer.wd3.myworkdayjobs.com/Svitzer_Careers"}},
            {"name": "KPMG", "source": {"type": "hrmanager", "customer": "kpmg"}}]
    keys = known_keys(emps)
    assert "workday:svitzer.wd3.myworkdayjobs.com/svitzer_careers" in keys and "hrmanager:kpmg" in keys


def test_company_from_title():
    assert company_from_title("Studentermedhjælper til CRM, Danske Spil A/S") == "Danske Spil A/S"
    assert company_from_title("Uden firma") == ""

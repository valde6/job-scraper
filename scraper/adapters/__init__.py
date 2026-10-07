"""Adaptere pr. rekrutteringssystem.

Hver adapter tager en virksomheds-config (dict fra companies.yaml) og returnerer
(antal_opslag_set, [Job, ...]) hvor listen kun indeholder danske studenterjob.
"""
from . import workday, successfactors, smartrecruiters, greenhouse, lever, teamtailor, \
    hrmanager, amazon, eightfold, oracle, generic, jobindex, phenom, browser

ADAPTERS = {
    "workday": workday.scrape,
    "successfactors": successfactors.scrape,
    "smartrecruiters": smartrecruiters.scrape,
    "greenhouse": greenhouse.scrape,
    "lever": lever.scrape,
    "teamtailor": teamtailor.scrape,
    "hrmanager": hrmanager.scrape,
    "amazon": amazon.scrape,
    "eightfold": eightfold.scrape,
    "oracle": oracle.scrape,
    "generic": generic.scrape,
    "jobindex": jobindex.scrape,
    "phenom": phenom.scrape,
    "browser": browser.scrape,
}

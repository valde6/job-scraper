"""Arbejdsgiveren i HR-Managers fælles portaler (Statens Rekrutteringsløsning, Statens eRekruttering)."""
import pytest

from scraper.adapters.hrmanager import employer_from_tree

PORTAL = "Statens Rekrutteringsløsning"


@pytest.mark.parametrize("path,expected", [
    (["Statens Rekrutteringsløsning", "§ 28 TRM (L-HR) - Transportministeriet", "Banedanmark", "Kommunikation"], "Banedanmark"),
    (["Statens Rekrutteringsløsning", "§7 FM (F-HR) - Finansministeriet", "Finansministeriets departement"], "Finansministeriet"),
    (["Statens Rekrutteringsløsning", "§7 FM (F-HR) - Finansministeriet"], "Finansministeriet"),
    (["Statens eRekruttering", "Statslige institutioner", "Udenrigsministeriet", "Institut for Menneskerettigheder",
      "Nationalt Område", "Juridisk Afdeling"], "Institut for Menneskerettigheder"),
    (["Statens eRekruttering", "Selvejende institutioner", "Undervisningsministeriet", "TEC"], "TEC"),
    (["Professionshøjskolen Absalon", "Rektor", "Center for Pædagogik"], "Professionshøjskolen Absalon"),
    (["Statens Rekrutteringsløsning", "§ 21 KUM (L-HR (Lille) - Kulturministeriet", "Det Danske Filminstitut"], "Det Danske Filminstitut"),
    (["Statens Rekrutteringsløsning", "Elever og praktikanter"], PORTAL),
    ([], PORTAL),
])
def test_employer_from_tree(path, expected):
    assert employer_from_tree(path, PORTAL) == expected


@pytest.mark.parametrize("path,expected", [
    (["Statens Rekrutteringsløsning", "§13 MSSB (K-HR) Ministeriet for Samfund og Beredskab"], "Ministeriet for Samfund og Beredskab"),
    (["Statens Rekrutteringsløsning", "§27 (F-HR) Ministeriet for Natur og Dyrevelfærd"], "Ministeriet for Natur og Dyrevelfærd"),
])
def test_ministry_without_dash(path, expected):
    assert employer_from_tree(path, PORTAL) == expected

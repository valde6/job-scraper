"""Emply (kunde.career.emply.com) – bruges af mange kommuner, foreninger, a-kasser og advokatfirmaer.

Config:
  url: https://aeldresagen.career.emply.com        (eller kundens eget domæne, fx https://job.frederiksberg.dk)
  path: /ledige-stillinger                         (valgfri; standard)
Listen bygges med JavaScript, så den læses med browseren; opslagene ligger under /ad/<slug>/<id>.
"""
from . import browser as browser_adapter

LINK_PATTERN = r"/ad/[^/?#]+/[a-z0-9]{5,8}"


def scrape(cfg):
    base = cfg["url"].rstrip("/")
    return browser_adapter.scrape({
        "name": cfg["name"],
        "urls": [base + cfg.get("path", "/ledige-stillinger")],
        "link_pattern": LINK_PATTERN,
        "dk_only": cfg.get("dk_only", True),
        "detail": cfg.get("detail", "browser"),
        "more_clicks": 5,
    })

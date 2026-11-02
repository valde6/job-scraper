import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import os

# Linkkontrollen (scraper/linkcheck.py) henter rigtige sider. Tests kører uden netværk; de tests, der afprøver den,
# giver selv en falsk fetcher.
os.environ.setdefault("JOBRADAR_LINKCHECK", "0")

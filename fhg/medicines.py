"""Indian medicine brand names → generic names and drug classes.

Prescriptions in India name brands ("Telma 40", "Glycomet GP 1", "Ecosprin AV 75"). Knowing the generic lets the
app show what the medicine is, merge the same medicine prescribed under different brands, and export a meaningful
FHIR MedicationStatement.

``data/india_medicines.csv`` is a curated starter list of common chronic-disease and everyday brands. It is
informational: verify against the manufacturer or CDSCO data before any clinical use. Extending it is a data change
(see docs/DATA_SOURCES.md for fuller sources such as CIMS/MIMS India).
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

DATA = Path(__file__).parent / "data" / "india_medicines.csv"
_FORM = re.compile(r"^(?:tab(?:let)?s?|cap(?:sule)?s?|syp|syr(?:up)?|inj(?:ection)?|oint(?:ment)?|drops?|susp|"
                   r"inhaler|inh|sachet|gel|cream)\b\.?\s*", re.I)


@dataclass(frozen=True)
class MedicineInfo:
    generic: str
    drug_class: str
    brand: Optional[str] = None


def _key(text: str) -> str:
    return re.sub(r"[\s\-_/]+", " ", text.lower()).strip()


@lru_cache(maxsize=1)
def _tables() -> tuple[dict[str, MedicineInfo], dict[str, MedicineInfo]]:
    brands, generics = {}, {}
    with DATA.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            info = MedicineInfo(row["generic"], row["drug_class"], row["brand"])
            brands[_key(row["brand"])] = info
            generics.setdefault(_key(row["generic"]), MedicineInfo(row["generic"], row["drug_class"]))
    return brands, generics


def lookup(name: str) -> Optional[MedicineInfo]:
    """Match a medicine as written ("Tab. Telma-H 40", "Glycomet GP 1", "Metformin 500 mg")."""
    brands, generics = _tables()
    text = _FORM.sub("", name.strip())
    text = re.sub(r"\(.*?\)", " ", text)
    words = []
    for w in _key(text).split():
        if re.match(r"^\d", w):
            break  # strength starts: "telma h 40" -> ["telma", "h"]
        words.append(re.sub(r"[^a-z0-9]", "", w))
    words = [w for w in words if w]
    for n in range(min(len(words), 3), 0, -1):  # longest brand first: "glycomet gp" before "glycomet"
        candidate = " ".join(words[:n])
        if candidate in brands:
            return brands[candidate]
        if candidate in generics:
            return generics[candidate]
    return None


def size() -> int:
    return len(_tables()[0])

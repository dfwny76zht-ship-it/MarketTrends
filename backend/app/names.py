"""Reading Hoya names from shop listings. Pure functions, no database."""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass, field

_QUOTES = str.maketrans({c: "'" for c in "‘’‚‛“”„\"´`"})

# Shop extras that say nothing about the plant itself.
_NOISE = [
    r"\bselten\b", r"\brare\b", r"\bbaby\s*plant\b", r"\bbabyplant\b", r"\bbaby\b",
    r"\bnew\b", r"\bneu\b", r"\bsale\b", r"\bangebot\b",
    r"\bstecklinge?\b", r"\bcuttings?\b", r"\b(?:un)?bewurzelt(?:e|er)?\b", r"\brooted\b",
    r"\bim\s+schneckenhaus\b", r"\bschneckenhaus\b",
    r"\b(?:h[äa]nge)?ampel\b", r"\brundtopf\b", r"\btopf\b", r"\bpot\b",
    r"\b\d+(?:[.,]\d+)?\s*cm\b", r"\bø\b",
]
_SIZE_SUFFIX = re.compile(r"\s+(xs|s|m|l|xl|xxl)\s*$", re.I)

COLLECTION_RE = re.compile(r"\b(IML|EPC|GPS|RB|SR|UT|CMB|AH|GB|DS|JM|PG|BS|NS)[\s\-.]?(\d{2,5}[A-Za-z]?)\b", re.I)

_QUALIFIERS = {
    "cv.": "cv", "cv": "cv", "var.": "var", "var": "var", "ssp.": "subsp", "ssp": "subsp",
    "subsp.": "subsp", "subsp": "subsp", "aff.": "aff", "aff": "aff", "cf.": "cf", "cf": "cf",
    "sp.": "sp", "sp": "sp", "spec.": "sp", "f.": "f",
}

FORM_WORDS = {
    "variegata", "variegated", "splash", "splashed", "albomarginata", "marginata", "albo",
    "tricolor", "tricolour", "inner", "outer", "silver",
}
_FORM_CANON = {"variegated": "Variegata", "splashed": "Splash", "tricolour": "Tricolor"}


def _clean(name: str) -> str:
    """Tidy a shop name but keep upper/lower case."""
    s = unicodedata.normalize("NFKC", name or "").translate(_QUOTES)
    s = re.sub(r"\s[–—-]\s", " ", s)
    for pat in _NOISE:
        s = re.sub(pat, " ", s, flags=re.I)
    s = re.sub(r"^\s*hoya\b", " ", s, flags=re.I)
    s = re.sub(r"[()\[\],;:]", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" .-")
    s = _SIZE_SUFFIX.sub("", s)
    return re.sub(r"\s+", " ", s).strip(" .-")


def name_key(name: str) -> str:
    """The spelling key: same key = same plant name, whatever the shop's extras."""
    return _clean(name).lower()


def _title(words: list[str]) -> str:
    return " ".join(w if any(c.isupper() for c in w[1:]) else w[:1].upper() + w[1:] for w in words)


@dataclass
class Parsed:
    epithet: str | None = None
    epithet_match: str = "none"  # exact | synonym | fuzzy | unknown | none
    epithet_written: str | None = None
    cultivar: str | None = None
    kind: str | None = None  # cultivar | form | subspecies | hybrid
    collection_no: str | None = None
    qualifiers: set[str] = field(default_factory=set)


def parse(name: str, epithets: set[str], synonyms: dict[str, str]) -> Parsed:
    s = _clean(name)
    p = Parsed()

    codes = COLLECTION_RE.findall(s)
    if codes:
        p.collection_no = f"{codes[0][0].upper()} {codes[0][1].upper()}"
        s = COLLECTION_RE.sub(" ", s)

    quoted = [q.strip() for q in re.findall(r"'([^']+)'", s) if q.strip()]
    s = re.sub(r"'[^']*'", " ", s)

    words = []
    for tok in s.split():
        q = _QUALIFIERS.get(tok.lower())
        if q:
            p.qualifiers.add(q)
        elif re.search(r"[A-Za-z]", tok):
            words.append(tok.strip("."))
    words = [w for w in words if w]

    rest = words
    if words and "sp" not in p.qualifiers and "cv" not in p.qualifiers:
        w0 = words[0].lower()
        if w0 in epithets:
            p.epithet, p.epithet_match = w0, "exact"
        elif w0 in synonyms:
            p.epithet, p.epithet_match = synonyms[w0], "synonym"
        elif len(w0) >= 5 and w0.isalpha():
            close = difflib.get_close_matches(w0, epithets, n=1, cutoff=0.85)
            if close:
                p.epithet, p.epithet_match = close[0], "fuzzy"
            elif words[0][0].islower():
                p.epithet, p.epithet_match = w0, "unknown"
        if p.epithet:
            p.epithet_written = w0
            rest = words[1:]

    if quoted:
        p.cultivar = quoted[0]
        p.kind = "cultivar" if p.epithet else "hybrid"
    elif rest:
        lowered = [w.lower() for w in rest]
        if p.epithet and ("subsp" in p.qualifiers or "var" in p.qualifiers):
            rank = "subsp." if "subsp" in p.qualifiers else "var."
            p.cultivar, p.kind = f"{rank} {lowered[0]}", "subspecies"
        elif all(w in FORM_WORDS for w in lowered):
            p.cultivar = " ".join(_FORM_CANON.get(w, w.capitalize()) for w in lowered)
            p.kind = "form"
        else:
            p.cultivar = _title(rest)
            p.kind = "cultivar" if p.epithet else "hybrid"
    return p


def size_class(pot_size: str | None, name: str | None = None) -> str:
    """Pot size in cm -> XS (≤6) / S (7–9) / M (10–12) / L (13–15) / XL (>15); else hints in the name."""
    m = re.search(r"(\d+(?:[.,]\d+)?)", pot_size or "")
    if m:
        cm = float(m.group(1).replace(",", "."))
        if cm <= 6.5:
            return "XS"
        if cm <= 9.5:
            return "S"
        if cm <= 12.5:
            return "M"
        if cm <= 15.5:
            return "L"
        return "XL"
    n = (name or "").lower()
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*cm", n)
    if m:
        return size_class(m.group(1))
    if re.search(r"\bbaby\s*plant\b|\bbabyplant\b|\bbaby\b", n):
        return "XS"
    m = _SIZE_SUFFIX.search(n.strip())
    if m:
        return {"xs": "XS", "s": "S", "m": "M", "l": "L", "xl": "XL", "xxl": "XL"}[m.group(1).lower()]
    return "unknown"

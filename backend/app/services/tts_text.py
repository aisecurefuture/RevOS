"""TTS text normalization — make arbitrary marketing copy safe for XTTS.

XTTS-v2's built-in text cleaner crashes or mispronounces on raw digits,
currency, and unusual characters (its sentence splitter uses the '∯' marker
internally, and its num2words pass fails on address-style numbers). Listing
scripts are full of exactly that — street numbers, prices, square footage,
phone numbers — so we normalize BEFORE synthesis and keep the human-readable
script untouched in the UI/DB.

Reading rules (tuned for real-estate copy):
  * $1,234,567   -> "one million two hundred thirty-four thousand five
                     hundred sixty-seven dollars"
  * 2,450        -> cardinal words (comma-grouped numbers are quantities)
  * 412          -> cardinal words (short bare numbers: street numbers, years)
  * 60655        -> "six zero six five five" (bare runs of 5+ digits are
                     ZIPs/phones — spoken digit-by-digit, like realtors do)
  * 2.5          -> "two point five"
  * Ave/Rd/St/N/S/E/W... -> expanded; USPS state codes -> full state names
  * &, %, #, exotic punctuation -> words or stripped

Pure and deterministic — unit-tested without any model.
"""

from __future__ import annotations

import re

_ONES = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen",
]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
_SCALES = [(1_000_000_000, "billion"), (1_000_000, "million"), (1_000, "thousand")]


def number_to_words(n: int) -> str:
    """0..999,999,999,999 as plain cardinal words (no 'and', no hyphens —
    XTTS handles flat word streams best)."""
    if n < 0:
        return "minus " + number_to_words(-n)
    if n < 20:
        return _ONES[n]
    if n < 100:
        tens, rem = divmod(n, 10)
        return _TENS[tens] + (f" {_ONES[rem]}" if rem else "")
    if n < 1000:
        hundreds, rem = divmod(n, 100)
        out = f"{_ONES[hundreds]} hundred"
        return out + (f" {number_to_words(rem)}" if rem else "")
    for scale, name in _SCALES:
        if n >= scale:
            major, rem = divmod(n, scale)
            out = f"{number_to_words(major)} {name}"
            return out + (f" {number_to_words(rem)}" if rem else "")
    return _ONES[0]  # unreachable


def _digits_spoken(digits: str) -> str:
    """'60655' -> 'six zero six five five'."""
    return " ".join(_ONES[int(d)] for d in digits)


# Street-suffix / directional abbreviations (with optional trailing period).
_ABBREVIATIONS = {
    "ave": "avenue", "blvd": "boulevard", "cir": "circle", "ct": "court",
    "dr": "drive", "hwy": "highway", "ln": "lane", "pkwy": "parkway",
    "pl": "place", "rd": "road", "sq": "square", "st": "street",
    "ter": "terrace", "trl": "trail",
    "n": "north", "s": "south", "e": "east", "w": "west",
    "ne": "northeast", "nw": "northwest", "se": "southeast", "sw": "southwest",
    "apt": "apartment", "ste": "suite", "sqft": "square feet",
    "ft": "feet", "mi": "miles",
}

_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska",
    "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "DC": "D C",
}

_KEEP_CHARS = re.compile(r"[^a-zA-Z0-9 .,!?']")
_WS = re.compile(r"\s+")


def _spell_currency(m: re.Match) -> str:
    whole = int(m.group(1).replace(",", ""))
    return f"{number_to_words(whole)} dollars"


def _spell_number(m: re.Match) -> str:
    raw = m.group(0)
    if "." in raw:
        whole, frac = raw.split(".", 1)
        whole_words = number_to_words(int(whole.replace(",", ""))) if whole else "zero"
        return f"{whole_words} point {_digits_spoken(frac)}"
    digits = raw.replace(",", "")
    # Bare runs of 5+ digits (no comma grouping) read as ZIP/phone: digit-by-digit.
    if "," not in raw and len(digits) >= 5:
        return _digits_spoken(digits)
    return number_to_words(int(digits))


def _expand_word(m: re.Match) -> str:
    word = m.group(0)
    if word in _STATES:  # exact-case USPS code ("IL", not "il"/"In")
        return _STATES[word]
    lower = word.lower()
    if lower in _ABBREVIATIONS:
        return _ABBREVIATIONS[lower]
    return word


def tts_normalize(text: str) -> str:
    """Human marketing copy -> XTTS-safe spoken text."""
    out = text
    # Unicode punctuation XTTS trips on.
    out = (
        out.replace("’", "'").replace("‘", "'")
        .replace("“", "").replace("”", "")
        .replace("—", ", ").replace("–", ", ").replace("…", ".")
    )
    out = out.replace("&", " and ").replace("%", " percent").replace("#", " number ")
    out = out.replace("+", " plus ").replace("@", " at ").replace("/", " ")

    # Currency first (so "$489,000" isn't split), then remaining numbers.
    out = re.sub(r"\$\s*([0-9][0-9,]*)(?:\.[0-9]{1,2})?", _spell_currency, out)
    out = re.sub(r"[0-9][0-9,]*\.[0-9]+|[0-9][0-9,]*", _spell_number, out)

    # Abbreviations / state codes, word by word (period-tolerant: "Ave." works
    # because the period is a word boundary and survives as sentence punct).
    out = re.sub(r"[A-Za-z]+", _expand_word, out)

    # Whatever's left that XTTS can't say, drop; collapse whitespace.
    out = _KEEP_CHARS.sub(" ", out)
    out = _WS.sub(" ", out).strip()
    return out

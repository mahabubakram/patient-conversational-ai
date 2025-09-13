import spacy
from negspacy.negation import Negex
import re
from typing import List, Optional
from .schema import Entity, ExtractionResult

def build_nlp():
    nlp = spacy.load("en_core_web_sm")      # small, fast model
    if not nlp.has_pipe("negex"):
        nlp.add_pipe("negex", last=True)    # adds negation flags to entities
    return nlp

NLP = build_nlp()

AGE_RE = re.compile(r"\b(\d{1,3})\s*(y(?:rs?|ears?)|yo|jahr(?:e|en)?)\b", re.I)
PREGNANCY_RE = re.compile(r"\b(pregnan\w*|schwanger)\b", re.I)

## days find out regex
DUR_HOURS_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*(hours?|hrs?|h)\b", re.I)
DUR_DAYS_RE  = re.compile(r"\b(\d+(?:\.\d+)?)\s*(days?|d)\b", re.I)
DUR_WEEKS_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*(weeks?|wks?|w)\b", re.I)
SINCE_YESTERDAY_RE = re.compile(r"\bsince\s+yesterday\b", re.I)
TODAY_RE = re.compile(r"\b(today|for a few hours)\b", re.I)
FEW_DAYS_RE = re.compile(r"\b(a\s*few\s*days|couple of days)\b", re.I)

def _parse_duration_days(text: str) -> Optional[float]:
    t = text.lower()
    m = DUR_HOURS_RE.search(t)
    if m:
        return float(m.group(1)) / 24.0
    m = DUR_DAYS_RE.search(t)
    if m:
        return float(m.group(1))
    m = DUR_WEEKS_RE.search(t)
    if m:
        return float(m.group(1)) * 7.0
    if SINCE_YESTERDAY_RE.search(t):
        return 1.0
    if TODAY_RE.search(t):
        return 0.5
    if FEW_DAYS_RE.search(t):
        return 3.0
    return None

def extract(text: str) -> ExtractionResult:
    doc = NLP(text)
    # heuristics first
    age = None
    m = AGE_RE.search(text)
    if m:
        try:
            age = int(m.group(1))
        except ValueError:
            age = None
    pregnant = bool(PREGNANCY_RE.search(text))

    duration_days = _parse_duration_days(text)

    # convert spaCy ents → our Entity list
    ents: List[Entity] = []
    for ent in doc.ents:
        negated = getattr(ent._, "negex", False) if hasattr(ent._, "negex") else False
        ents.append(Entity(
            type=ent.label_.upper(),
            text=ent.text,
            negated=bool(negated),
            start=ent.start_char,
            end=ent.end_char
        ))
    return ExtractionResult(age=age, pregnant=pregnant, entities=ents, duration_days=duration_days)


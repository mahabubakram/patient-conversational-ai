import spacy
from negspacy.negation import Negex
import re
from typing import List
from .schema import Entity, ExtractionResult

def build_nlp():
    nlp = spacy.load("en_core_web_sm")      # small, fast model
    if not nlp.has_pipe("negex"):
        nlp.add_pipe("negex", last=True)    # adds negation flags to entities
    return nlp

NLP = build_nlp()

AGE_RE = re.compile(r"\b(\d{1,3})\s*(y(?:rs?|ears?)|yo|jahr(?:e|en)?)\b", re.I)
PREGNANCY_RE = re.compile(r"\b(pregnan\w*|schwanger)\b", re.I)

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
    print(len(doc.ents))

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
    return ExtractionResult(age=age, pregnant=pregnant, entities=ents)


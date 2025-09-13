from typing import Optional, Tuple, Dict
from app.nlu.schema import ExtractionResult
import re

EMERGENCY_KEYWORDS = {
    "chest pain","pressure in chest","shortness of breath","can't breathe","cant breathe",
    "severe bleeding","fainted","pass out","stroke","weakness one side","numbness one side",
    "seizure","anaphylaxis","swollen tongue","suicidal","suicide",
}
URGENT_KEYWORDS = {
    "stiff neck","worst headache","pregnant bleeding",
    "flank pain","blood in urine","cannot keep fluids",
}

# --- tiny helper to avoid obvious negation like "no chest pain" or "denies chest pain"
def _present(text: str, kw: str) -> bool:
    t = text.lower()
    # kw as a loose regex (word-boundary where it helps)
    kw_re = re.escape(kw)
    if re.search(rf"\b(no|denies|without)\s+{kw_re}\b", t):
        return False
    return re.search(rf"\b{kw_re}\b", t) is not None

def _any(text: str, kws: list[str]) -> bool:
    return any(_present(text, k) for k in kws)

def _both(text: str, a: list[str], b: list[str]) -> bool:
    return _any(text, a) and _any(text, b)

# ----- helpers -----
def _present(text: str, kw: str) -> bool:
    """Return True if kw is present and not obviously negated (e.g., 'no chest pain')."""
    t = text.lower()
    kw_re = re.escape(kw)
    if re.search(rf"\b(no|denies|without)\s+{kw_re}\b", t):
        return False
    return re.search(rf"\b{kw_re}\b", t) is not None

def _any(text: str, kws: list[str]) -> bool:
    return any(_present(text, k) for k in kws)

def _both(text: str, a: list[str], b: list[str]) -> bool:
    return _any(text, a) and _any(text, b)

# ----- rich checker (new) -----
def check_red_flags_detail(text: str, ext: ExtractionResult) -> Optional[Dict]:
    """
    Returns a structured escalation payload if a red flag is detected, else None.
    Shape: {"status","message","next_step","rationale"}
    """
    t = text.lower()

    # EMERGENCY — cardio/resp combo
    if _any(t, ["crushing chest pain", "chest pain"]) and _any(t, ["shortness of breath", "cant breathe", "can’t breathe", "breathless"]):
        return {
            "status": "EMERGENCY",
            "message": "Your symptoms could be serious. Please call 112 or go to the nearest emergency department now.",
            "next_step": "Call 112 / go to ER.",
            "rationale": "red_flags: chest pain + shortness of breath",
        }

    # EMERGENCY — neuro
    if _any(t, ["worst headache of my life", "worst headache", "thunderclap headache"]):
        return {
            "status": "EMERGENCY",
            "message": "Severe sudden headache can be serious. Please call 112 or go to the ER.",
            "next_step": "Call 112 / go to ER.",
            "rationale": "red_flags: worst headache",
        }
    if _both(t, ["stiff neck", "neck stiffness"], ["fever", "high fever"]):
        return {
            "status": "EMERGENCY",
            "message": "Fever with stiff neck needs urgent assessment. Please call 112 or go to the ER.",
            "next_step": "Call 112 / go to ER.",
            "rationale": "red_flags: fever + stiff neck",
        }
    if _any(t, ["confusion", "disoriented", "slurred speech", "weakness on one side", "numbness on one side", "face droop", "vision loss", "seizure"]):
        return {
            "status": "EMERGENCY",
            "message": "Neurologic symptoms need emergency care. Please call 112 or go to the ER.",
            "next_step": "Call 112 / go to ER.",
            "rationale": "red_flags: acute neurologic symptom",
        }

    # EMERGENCY — anaphylaxis
    if _any(t, ["tongue swelling", "lip swelling", "swollen tongue", "swollen lips"]) or \
       _both(t, ["hives", "widespread rash"], ["shortness of breath", "wheeze", "trouble breathing"]):
        return {
            "status": "EMERGENCY",
            "message": "Possible severe allergic reaction. Call 112 or go to the ER immediately.",
            "next_step": "Call 112 / go to ER.",
            "rationale": "red_flags: anaphylaxis features",
        }

    # EMERGENCY — pregnancy + severe symptom
    if ext.pregnant and _any(t, ["severe abdominal pain", "heavy bleeding", "vaginal bleeding"]):
        return {
            "status": "EMERGENCY",
            "message": "During pregnancy, severe pain or bleeding needs emergency care. Call 112 or go to the ER.",
            "next_step": "Call 112 / go to ER.",
            "rationale": "red_flags: pregnancy + severe symptom",
        }

    # EMERGENCY — pediatrics: infant < 3 months + fever
    if ext.age is not None and ext.age < 3 and _any(t, ["fever", "temperature", "high fever"]):
        return {
            "status": "EMERGENCY",
            "message": "Fever in a baby under 3 months needs emergency assessment. Call 112 or go to the ER.",
            "next_step": "Call 112 / go to ER.",
            "rationale": "red_flags: infant (<3 months) + fever",
        }

    # EMERGENCY — overdose/poisoning
    if _any(t, ["overdose", "took too many pills", "took too much", "ingested bleach", "ingested chemical", "poisoned", "drank poison"]):
        return {
            "status": "EMERGENCY",
            "message": "Possible poisoning/overdose. Call 112 or contact emergency services immediately.",
            "next_step": "Call 112 / go to ER.",
            "rationale": "red_flags: overdose/poisoning",
        }

    # --- EMERGENCY: serious trauma / head injury + LOC or vomiting
    # More flexible patterns: allow "fell down the stairs", "fell from", "hit my head", etc.
    trauma_fall_patterns = [
        r"\bfell\s+down\s+(the\s+)?stairs\b",
        r"\bfell\s+from\b",
        r"\bserious\s+fall\b",
        r"\bhead\s+injury\b",
        r"\bhit\s+my\s+head\b",
        r"\bknocked\s+my\s+head\b",
    ]
    loc_or_vomit_words = [
        "loss of consciousness", "lost consciousness", "passed out",
        "blacked out", "knocked out", "vomiting", "throwing up", "threw up"
    ]

    trauma_fall = any(re.search(p, t) for p in trauma_fall_patterns)
    loc_or_vomit = _any(t, loc_or_vomit_words)

    if trauma_fall and loc_or_vomit:
        return {
            "status": "EMERGENCY",
            "message": "Head injury with concerning features needs emergency care. Call 112 or go to the ER.",
            "next_step": "Call 112 / go to ER.",
            "rationale": "red_flags: trauma + LOC/vomiting",
        }

    # EMERGENCY — mental health crisis
    if _any(t, ["suicidal", "kill myself", "harmed myself", "self-harm", "can't stay safe", "cant stay safe"]):
        return {
            "status": "EMERGENCY",
            "message": "You deserve immediate support. If you are in danger, call 112 now. If you can, seek urgent help from local crisis services.",
            "next_step": "Call 112 / go to ER.",
            "rationale": "red_flags: mental health crisis",
        }

    # URGENT — UTI with systemic/kidney signs
    if _both(t, ["burning urination", "painful urination", "dysuria"], ["fever", "back pain", "flank pain"]):
        return {
            "status": "URGENT",
            "message": "Urinary symptoms with fever or back/flank pain need same-day care.",
            "next_step": "Seek same-day urgent care or contact your GP today.",
            "rationale": "red_flags: UTI with systemic features",
        }

    # Fallback to any legacy keyword lists (if you want to keep them)
    for kw in EMERGENCY_KEYWORDS:
        if _present(t, kw):
            return {
                "status": "EMERGENCY",
                "message": "Your symptoms may be serious. Please call 112 / go to ER.",
                "next_step": "Call 112 / go to ER.",
                "rationale": f"red_flags: {kw}",
            }
    for kw in URGENT_KEYWORDS:
        if _present(t, kw):
            return {
                "status": "URGENT",
                "message": "Your symptoms may need same-day care.",
                "next_step": "Seek urgent care / contact your GP today.",
                "rationale": f"red_flags: {kw}",
            }

    return None

# ----- wrapper (legacy API) -----
def check_red_flags(text: str, ext: ExtractionResult) -> Tuple[str, Optional[str]]:
    """
    Backward-compatible wrapper. Returns (status, rationale_or_none).
    Keeps your old triage code working without changes.
    """
    hit = check_red_flags_detail(text, ext)
    if hit is None:
        return "SAFE", None
    return hit["status"], hit.get("rationale")
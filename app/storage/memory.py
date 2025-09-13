# app/storage/memory.py
from dataclasses import dataclass
from typing import Optional, Dict
import re

@dataclass
class SessionState:
    age: Optional[int] = None               # one "slot" we care about for Sprint 1
    last_symptoms_text: Optional[str] = None  # what the user said about symptoms
    severity: Optional[str] = None # "mild" | "moderate" | "severe" | "worst"
    duration_days: Optional[float] = None

# Simple in-process store: resets on server restart (OK for POC)
SESSIONS: Dict[str, SessionState] = {}


def get_session(session_id: str) -> SessionState:
    """Return existing session or create a new empty one."""
    if session_id not in SESSIONS:
        SESSIONS[session_id] = SessionState()
    return SESSIONS[session_id]

_AGE_RE = re.compile(r"\b(\d{1,3})\s*(y(?:rs?|ears?)|yo|jahr(?:e|en)?|m(?:o|onths?))\b", re.I)

# Recognize canonical severity words and a few common synonyms
_SEVERITY_CANON = {
    "mild": "mild",
    "light": "mild",
    "not bad": "mild",
    "okayish": "mild",

    "moderate": "moderate",
    "medium": "moderate",
    "so-so": "moderate",

    "severe": "severe",
    "strong": "severe",
    "intense": "severe",

    "worst": "worst",
    "very severe": "worst",
}

# Build a regex that matches any key as a whole word sequence
_SEVERITY_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in sorted(_SEVERITY_CANON.keys(), key=len, reverse=True)) + r")\b",
    re.I
)

SYMPTOM_WORDS = [
    "cough","fever","sore throat","headache","abdominal","stomach","vomit",
    "diarrhea","rash","ear pain","urination","back pain","shortness of breath",
]

def parse_age(text: str) -> Optional[int]:
    m = _AGE_RE.search(text)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None

def parse_severity(text: str) -> Optional[str]:
    m = _SEVERITY_RE.search(text)
    if not m:
        return None
    return _SEVERITY_CANON[m.group(1).lower()]

def looks_like_symptoms(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in SYMPTOM_WORDS)

def merge_turn(session: SessionState, user_text: str) -> None:
    """Update slots from this turn: age and (if present) the latest symptom text."""
    age = parse_age(user_text)
    if age is not None:
        session.age = age

    sev = parse_severity(user_text)
    if sev is not None:
        session.severity = sev

    dur = parse_duration_days(user_text)
    if dur is not None:
        session.duration_days = dur


    if looks_like_symptoms(user_text):
        # For simplicity, replace the last symptom text with the latest description
        session.last_symptoms_text = user_text.strip()

def build_effective_text(session: SessionState, current_text: str) -> str:
    """What text should the triage engine see this turn?"""
    has_symptoms_now = looks_like_symptoms(current_text)
    parts = []

    # If we have age in the session, always include it up front (strict age policy)
    if session.age is not None:
        parts.append(f"{session.age} years old.")
    # include severity if known (helps satisfy the policy check)
    if session.severity is not None:
        parts.append(f"Severity: {session.severity}")
    if session.duration_days is not None:
        parts.append(f"Duration: {session.duration_days} days.")


    # If user didn't repeat symptoms this turn, use last known symptoms
    if has_symptoms_now:
        parts.append(current_text.strip())
    elif session.last_symptoms_text:
        parts.append(session.last_symptoms_text)

    # If nothing to base on, fall back to current text
    if not parts:
        parts.append(current_text.strip())

    return " ".join(parts).strip()

# --- add duration regexes (copy of extractor’s simplified) ---
_DUR_HOURS_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*(hours?|hrs?|h)\b", re.I)
_DUR_DAYS_RE  = re.compile(r"\b(\d+(?:\.\d+)?)\s*(days?|d)\b", re.I)
_DUR_WEEKS_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*(weeks?|wks?|w)\b", re.I)
_SINCE_YESTERDAY_RE = re.compile(r"\bsince\s+yesterday\b", re.I)
_TODAY_RE = re.compile(r"\b(today|for a few hours)\b", re.I)
_FEW_DAYS_RE = re.compile(r"\b(a\s*few\s*days|couple of days)\b", re.I)


def parse_duration_days(text: str) -> Optional[float]:
    t = text.lower()
    m = _DUR_HOURS_RE.search(t)
    if m: return float(m.group(1)) / 24.0
    m = _DUR_DAYS_RE.search(t)
    if m: return float(m.group(1))
    m = _DUR_WEEKS_RE.search(t)
    if m: return float(m.group(1)) * 7.0
    if _SINCE_YESTERDAY_RE.search(t): return 1.0
    if _TODAY_RE.search(t): return 0.5
    if _FEW_DAYS_RE.search(t): return 3.0
    return None


from typing import Dict, Optional
from app.nlu.schema import ExtractionResult
from app.policies.red_flags import check_red_flags
from app.retrieval.index import search

SAFE_LANGUAGE = (
    "This is not a diagnosis. If symptoms worsen or new red flags appear, seek medical care promptly."
)

def _needs_followup(text: str, ext: ExtractionResult, ctx: dict | None = None) -> Optional[str]:
    """
    Decide whether we must ask for more info before giving guidance.

    Strict policy for Sprint 2:
      1) We require a *symptom* to be stated.
      2) We require *duration* (normalized in session as duration_days).
      3) We require *age*.
      4) We require *severity* (mild/moderate/severe/worst).

    We use slot flags from `ctx` so we don't re-ask across turns:
      ctx = {"has_age": bool, "has_severity": bool, "has_duration": bool}

    Returns:
      - a question string (ASK) if something essential is missing
      - None if we have enough info to proceed to retrieval/reasoning (SAFE/URGENT/EMERGENCY decided elsewhere)
    """
    ctx = ctx or {}
    has_age = bool(ctx.get("has_age"))
    has_severity = bool(ctx.get("has_severity"))
    has_duration = bool(ctx.get("has_duration"))

    t = text.lower().strip()

    # 0) Must contain at least one symptom-ish cue
    symptom_keywords = [
        "cough", "fever", "sore throat", "headache", "abdominal", "stomach", "vomit",
        "diarrhea", "rash", "ear pain", "urination", "back pain", "shortness of breath",
        "breathless", "dysuria", "chills", "congestion", "runny nose", "nausea",
    ]
    if not any(k in t for k in symptom_keywords):
        return "What is your main symptom (e.g., cough, fever, sore throat, headache, stomach pain)?"

    # 1) Duration (slot-first): if we don't have normalized duration yet, ask for it
    if not has_duration:
        return "How long have you had these symptoms (hours, days, or weeks)?"

    # 2) Age (strict)
    if not has_age:
        return "How old are you (in months if under 1 year, otherwise in years)?"

    # 3) Severity (strict). Accept either slot or explicit words in current text.
    mentions_severity = any(w in t for w in ("mild", "moderate", "severe", "worst"))
    if not has_severity and not mentions_severity:
        return "How severe is it (mild, moderate, or severe)?"

    # All required info present → proceed
    return None


def triage(text: str, ext: ExtractionResult, ctx: dict | None = None) -> Dict:
    # 1) Safety gate
    status, reason = check_red_flags(text, ext)
    if status == "EMERGENCY":
        return {
            "status": "EMERGENCY",
            "message": f"Emergency suspected: {reason or 'red flag detected'}. Call 112 or go to the ER now.",
            "categories": [],
            "next_step": "Call emergency services immediately.",
            "rationale": reason or "red flags present",
            "disclaimer": SAFE_LANGUAGE,
        }
    if status == "URGENT":
        hits = search(text, top_k=2)
        rationale = " ".join([h[1] for h in hits]) if hits else "Urgent pattern detected."
        return {
            "status": "URGENT",
            "message": "Same-day medical evaluation is recommended.",
            "categories": ["Possible acute condition"],
            "next_step": "Seek urgent care or contact your GP today.",
            "rationale": rationale[:800],
            "disclaimer": SAFE_LANGUAGE,
        }

    # 2) Agentic next action: ask if key info is missing
    q = _needs_followup(text, ext, ctx)
    if q:
        return {
            "status": "ASK",
            "message": q,
            "categories": [],
            "next_step": "",
            "rationale": "Key information missing for safe guidance.",
            "disclaimer": SAFE_LANGUAGE,
        }

    # 3) Retrieve snippets and compose final suggestion
    hits = search(text, top_k=3)
    categories = []
    for _id, _doc, meta in hits:
        tags_str = meta.get("tags") or ""
        if tags_str:
            first_tag = tags_str.split(",")[0].strip()
        else:
            first_tag = meta.get("path", _id)
        categories.append(first_tag.replace("_", " "))

    rationale = " ".join([h[1] for h in hits]) if hits else "General self-care advice."
    next_step = "Self-care and monitor; see GP if not improving in 3–7 days or if red flags appear."

    return {
        "status": "SAFE",
        "message": "Based on what you shared, here are possible categories and a safe next step.",
        "categories": categories[:3],
        "next_step": next_step,
        "rationale": rationale[:900],
        "disclaimer": SAFE_LANGUAGE,
    }

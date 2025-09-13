from typing import Dict, Optional
from app.nlu.schema import ExtractionResult
from app.policies.red_flags import check_red_flags
from app.retrieval.index import search

SAFE_LANGUAGE = (
    "This is not a diagnosis. If symptoms worsen or new red flags appear, seek medical care promptly."
)

def _needs_followup(text: str, ext: ExtractionResult) -> Optional[str]:
    t = text.lower()
    if ext.age is None and not any(k in t for k in ["year","yo","jahre","months","mo"]):
        return "How old are you (in months if under 1 year, otherwise in years)?"
    if not any(k in t for k in ["cough","fever","sore throat","headache","abdominal","vomit",
                                "diarrhea","rash","ear pain","urination","back pain","shortness of breath"]):
        return "What is your main symptom (e.g., cough, fever, sore throat, headache, stomach pain)?"
    if not any(k in t for k in ["day","days","week","weeks","since","yesterday","today"]):
        return "How long have you had these symptoms (hours, days, or weeks)?"
    if not any(k in t for k in ["mild","moderate","severe","worst"]):
        return "How severe is it (mild, moderate, or severe)?"
    return None

def triage(text: str, ext: ExtractionResult) -> Dict:
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
    q = _needs_followup(text, ext)
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

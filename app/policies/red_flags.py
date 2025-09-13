from typing import Optional, Tuple
from app.nlu.schema import ExtractionResult

EMERGENCY_KEYWORDS = {
    "chest pain","pressure in chest","shortness of breath","can't breathe","cant breathe",
    "severe bleeding","fainted","pass out","stroke","weakness one side","numbness one side",
    "seizure","anaphylaxis","swollen tongue","suicidal","suicide",
}
URGENT_KEYWORDS = {
    "stiff neck","worst headache","pregnant bleeding",
    "flank pain","blood in urine","cannot keep fluids",
}

def check_red_flags(text: str, ext: ExtractionResult) -> Tuple[str, Optional[str]]:
    t = text.lower()

    # age-based: infant <3 months with fever
    if ext.age is not None and ext.age < 3 and ("fever" in t or "temperature" in t):
        return "EMERGENCY", "Infant <3 months with fever"

    # pregnancy severe symptoms
    if ext.pregnant and ("bleeding" in t or "severe abdominal pain" in t):
        return "EMERGENCY", "Pregnant with bleeding or severe abdominal pain"

    for kw in EMERGENCY_KEYWORDS:
        if kw in t:
            return "EMERGENCY", f"Detected red flag: {kw}"

    # UTI with systemic signs
    if ("urine" in t or "urination" in t or "burning" in t) and ("fever" in t or "back pain" in t or "flank" in t):
        return "URGENT", "Possible kidney involvement (UTI + systemic signs)"

    for kw in URGENT_KEYWORDS:
        if kw in t:
            return "URGENT", f"Detected urgent symptom: {kw}"

    return "SAFE", None
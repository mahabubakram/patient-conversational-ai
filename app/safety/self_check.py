from dataclasses import dataclass
from typing import Literal, Dict

Action = Literal["APPROVE", "REWRITE", "BLOCK"]

@dataclass
class SafetyVerdict:
    action: Action
    text: str | None = None
    reason: str | None = None

FORBIDDEN_DIAGNOSTIC = ["you have ", "this is definitely", "guaranteed", "diagnosis is"]
FORBIDDEN_MEDS = ["antibiotic", "amoxicillin", "penicillin", "ibuprofen 800", "prescription"]
REQUIRE_DISCLAIMER_SNIPPET = "not a diagnosis"

def review(draft: Dict, context: Dict | None = None) -> SafetyVerdict:
    """
    Draft shape we expect (from triage):
      {"status","message","categories","next_step","rationale","disclaimer"}
    """
    context = context or {}
    text = f"{draft.get('message','')} {draft.get('next_step','')} {draft.get('disclaimer','')}".lower()

    # Block: explicit unsafe med advice or definitive diagnosis wording
    if any(kw in text for kw in FORBIDDEN_MEDS):
        return SafetyVerdict("BLOCK", text="For safety, I can’t provide medication instructions. Please see a clinician.", reason="meds")
    if any(kw in text for kw in FORBIDDEN_DIAGNOSTIC):
        safer = draft.copy()
        safer["message"] = "Based on what you shared, this can be due to several common causes. "
        return SafetyVerdict("REWRITE", text=safer["message"], reason="diagnostic_claim")

    # Require disclaimer; if missing or doesn’t contain the snippet, add it
    if REQUIRE_DISCLAIMER_SNIPPET not in (draft.get("disclaimer","").lower()):
        return SafetyVerdict("REWRITE", text=None, reason="missing_disclaimer")

    return SafetyVerdict("APPROVE")

from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Dict, Any
import json

from app.safety.config import SAFETY_LLM, SAFETY_LLM_MODEL, SAFETY_LLM_TIMEOUT, OPENAI_API_KEY
from app.safety.prompt_safety import SAFETY_SYSTEM_PROMPT

Action = Literal["APPROVE", "REWRITE", "BLOCK"]

@dataclass
class SafetyVerdict:
    action: Action
    text: str | None = None
    reason: str | None = None

# ---------- Rule-based STUB (existing behavior) ----------
FORBIDDEN_DIAGNOSTIC = ["you have ", "this is definitely", "guaranteed", "diagnosis is"]
FORBIDDEN_MEDS = ["antibiotic", "amoxicillin", "penicillin", "ibuprofen 800", "prescription"]
REQUIRE_DISCLAIMER_SNIPPET = "not a diagnosis"

def _review_stub(draft: Dict, context: Dict | None = None) -> SafetyVerdict:
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

# ---------- JSON extraction helper ----------
def _first_json_object(s: str) -> Dict[str, Any]:
    # Robust-ish: pick the first {...} blob
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object in response")
    snippet = s[start:end+1]
    return json.loads(snippet)

# ---------- LLM path ----------
def _review_llm(draft: Dict[str, Any]) -> SafetyVerdict:
    # Lazy import; keep optional
    try:
        from openai import OpenAI
    except Exception as e:
        raise RuntimeError(f"openai_import_failed: {e}")

    if not OPENAI_API_KEY:
        raise RuntimeError("missing_openai_key")
    ss = OPENAI_API_KEY

    client = OpenAI(api_key=OPENAI_API_KEY)  # uses OPENAI_API_KEY from env
    # Build the single message content with our DRAFT JSON
    user_content = json.dumps({"DRAFT": draft}, ensure_ascii=False)

    # Prefer the JSON response format if supported; fallback to plain text
    try:
        resp = client.chat.completions.create(
            model=SAFETY_LLM_MODEL,
            temperature=0,
            timeout=SAFETY_LLM_TIMEOUT,
            messages=[
                {"role":"system","content": SAFETY_SYSTEM_PROMPT},
                {"role":"user","content": user_content},
            ]
        )
        content = resp.choices[0].message.content or ""
    except Exception as e:
        # Any error → the caller will fallback to stub
        raise RuntimeError(f"llm_call_failed: {type(e).__name__}: {e}")

    try:
        data = _first_json_object(content)
        action = data.get("action", "").upper()
        reason = data.get("reason") or ""
        text = data.get("text") or ""
        if action not in ("APPROVE", "REWRITE", "BLOCK"):
            raise ValueError(f"bad_action: {action}")
        return SafetyVerdict(action=action, text=text, reason=reason)
    except Exception as e:
        # JSON parse failure → let caller fallback to stub
        raise RuntimeError(f"llm_parse_failed: {type(e).__name__}: {e}")

# ---------- Public API ----------
def review(draft: Dict[str, Any], context: Dict[str, Any] | None = None) -> SafetyVerdict:
    """
    Try LLM review if enabled; otherwise use the rule-based stub.
    Never raise to caller: on any failure, return the stub’s verdict.
    """
    # BLOCK as medication given
    #draft["message"] = "take medication ibuprofen 20mg " + draft.get("message")

    # If any of the prereqs are missing, go stub immediately
    use_llm = SAFETY_LLM and bool(OPENAI_API_KEY)
    if use_llm:
        try:
            return _review_llm(draft)
        except Exception:
            # Swallow and fallback to stub
            pass
    return _review_stub(draft)
import os
import pytest
from app.safety.self_check import review

llm_enabled = os.getenv("SAFETY_LLM","0") == "1" and os.getenv("OPENAI_API_KEY")

@pytest.mark.skipif(not llm_enabled, reason="SAFETY_LLM not enabled or key missing")
def test_llm_review_approve_like():
    draft = {
        "status": "SAFE",
        "message": "Based on what you shared, simple self-care may help.",
        "next_step": "Rest, fluids, analgesia per label.",
        "disclaimer": "This is not a diagnosis; not for emergencies.",
    }
    v = review(draft, context={})
    assert v.action in ("APPROVE", "REWRITE")

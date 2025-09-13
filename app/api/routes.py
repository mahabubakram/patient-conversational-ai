from fastapi import APIRouter, Query
from pydantic import BaseModel
from app.nlu.extractor import extract
from app.reasoner.triage import triage
from app.safety.disclaimers import DISCLAIMER
from app.storage.memory import get_session, merge_turn, build_effective_text
from app.safety.self_check import review as safety_review, SafetyVerdict

router = APIRouter(tags=["api"])

class ChatIn(BaseModel):
    message: str

class ChatOut(BaseModel):
    status: str
    reply: str
    categories: list[str] = []
    next_step: str = ""
    rationale: str = ""
    disclaimer: str = DISCLAIMER

@router.get("/")
async def root():
    return {"message": "Hello World"}

@router.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}
@router.post("/chat", response_model=ChatOut)
def chat(payload: ChatIn, session_id: str = Query("default")):
    # 1) Load session and merge this turn
    sess = get_session(session_id)
    merge_turn(sess, payload.message)

    # 2) Build effective text (strict age: include session age if available)
    effective_text = build_effective_text(sess, payload.message)
    ctx = {
        "has_age": sess.age is not None,
        "has_severity": sess.severity is not None,
        "has_duration": sess.duration_days is not None,
    }

    # 3) Extract + triage on the effective text
    ext = extract(effective_text)
    result = triage(effective_text, ext, ctx=ctx)

    # --- Safety self-check here ---
    verdict = safety_review(result, context={"session_id": session_id})
    if verdict.action == "APPROVE":
        pass  # use result as-is
    elif verdict.action == "REWRITE":
        # two common rewrites:
        if verdict.reason == "missing_disclaimer":
            result[
                "disclaimer"] = "Educational guidance only; not a diagnosis; not for emergencies. If this is an emergency, call 112."
        elif verdict.text:
            result["message"] = verdict.text
        # keep status/next_step unchanged
    elif verdict.action == "BLOCK":
        # fail-safe: ask or escalate generically
        result = {
            "status": "ASK",
            "message": "For safety, I need more information before I can guide you. Can you describe your symptoms and duration?",
            "categories": [],
            "next_step": "",
            "rationale": "blocked_by_safety_checker",
            "disclaimer": result.get(
                "disclaimer") or "Educational guidance only; not a diagnosis; not for emergencies. If this is an emergency, call 112.",
        }

    return ChatOut(
        status=result["status"],
        reply=result["message"],
        categories=result.get("categories", []),
        next_step=result.get("next_step", ""),
        rationale=result.get("rationale", "")[:900],
        disclaimer=result.get("disclaimer", DISCLAIMER),
    )

from fastapi import APIRouter, Query
from pydantic import BaseModel
from app.nlu.extractor import extract
from app.reasoner.triage import triage
from app.safety.disclaimers import DISCLAIMER
from app.storage.memory import get_session, merge_turn, build_effective_text
from app.safety.self_check import review as safety_review, SafetyVerdict
import time
from app.observability.metrics import (
    timer_start, timer_observe_ms, record_status, record_safety, record_error
)
import uuid
from app.observability.logs import log_event

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
    t0 = timer_start()
    safety_action = None
    try:
        # 1) Load/merge session, build effective text (as you already do)
        sess = get_session(session_id)
        merge_turn(sess, payload.message)
        effective_text = build_effective_text(sess, payload.message)

        # 2) Build ctx (slot flags)
        ctx = {
            "has_age": sess.age is not None,
            "has_severity": sess.severity is not None,
            "has_duration": getattr(sess, "duration_days", None) is not None,
        }
        # Logging
        request_id = str(uuid.uuid4())
        log_event(
            "triage_request",
            request_id=request_id,
            session_id=session_id,
            asked_slots={
                "age": bool(ctx["has_age"]),
                "severity": bool(ctx["has_severity"]),
                "duration": bool(ctx["has_duration"]),
            },
            # DO NOT include payload.message here (PII)
        )

        # 3) Extract + reason
        ext = extract(effective_text)
        result = triage(effective_text, ext, ctx=ctx)

        # 4) Safety self-check
        verdict = safety_review(result, context={"session_id": session_id})
        safety_action = verdict.action

        if verdict.action == "APPROVE":
            pass
        elif verdict.action == "REWRITE":
            if verdict.reason == "missing_disclaimer":
                result["disclaimer"] = "Educational guidance only; not a diagnosis; not for emergencies. If this is an emergency, call 112."
            elif verdict.text:
                result["message"] = verdict.text
        elif verdict.action == "BLOCK":
            result = {
                "status": "ASK",
                "message": "For safety, I need more information before I can guide you. Can you describe your symptoms and duration?",
                "categories": [],
                "next_step": "",
                "rationale": "blocked_by_safety_checker",
                "disclaimer": result.get("disclaimer") or "Educational guidance only; not a diagnosis; not for emergencies. If this is an emergency, call 112.",
            }

        # 5) Observe metrics
        elapsed_ms = timer_observe_ms(t0)
        record_safety(safety_action)
        record_status(result["status"])

        # Log Response
        log_event(
            "triage_response",
            request_id=request_id,
            session_id=session_id,
            status=result["status"],
            safety_action=safety_action,
            elapsed_ms=round(elapsed_ms, 2),
            categories=result.get("categories", []),
        )


        return ChatOut(
            status=result["status"],
            reply=result["message"],
            categories=result.get("categories", []),
            next_step=result.get("next_step", ""),
            rationale=result.get("rationale", "")[:900],
            disclaimer=result.get("disclaimer", DISCLAIMER),
        )

    except Exception as e:
        # Count the error and rethrow (FastAPI will turn into 500)
        record_error(type(e).__name__)
        timer_observe_ms(t0)
        log_event(
            "triage_error",
            request_id=request_id,
            session_id=session_id,
            error_type=type(e).__name__,
        )
        raise


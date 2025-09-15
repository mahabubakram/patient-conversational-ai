from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
import uuid

from app.nlu.extractor import extract
from app.reasoner.triage import triage
from app.safety.disclaimers import DISCLAIMER
from app.storage.memory import get_session, merge_turn, build_effective_text
from app.safety.self_check import review as safety_review
from app.observability.metrics import (
    timer_start, timer_observe_ms, record_status, record_safety, record_error
)
from app.observability.logs import log_event
from app.retrieval.index import search as rag_search

router = APIRouter(tags=["api"])


class ChatIn(BaseModel):
    message: str


class ChatOut(BaseModel):
    status: str
    reply: str
    categories: list[str] = Field(default_factory=list)
    next_step: str = ""
    rationale: str = ""
    disclaimer: str = DISCLAIMER


@router.get("/")
async def root():
    return {"message": "Hello World"}


@router.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}


def _categories_from_docs(docs: list[dict]) -> list[str]:
    """Derive category tags from retrieval docs' metadata."""
    cats: list[str] = []
    for d in docs or []:
        meta = d.get("meta", {}) if isinstance(d, dict) else {}
        # tags saved as a comma-separated string during ingest
        for t in (meta.get("tags") or "").split(","):
            t = t.strip().lower()
            if t and t not in cats:
                cats.append(t)
        topic = (meta.get("topic") or "").strip().lower()
        if topic and topic not in cats:
            cats.append(topic)
    return cats[:6]


def _finalize_payload(result: dict, effective_text: str) -> dict:
    """
    Guarantee API contract fields and fill safe defaults.
    Ensures: status, message (reply), categories, next_step, rationale, disclaimer.
    Never raises, even if RAG fails.
    """
    result = dict(result or {})

    # Unify key names
    if "message" not in result and "reply" in result:
        result["message"] = result["reply"]

    # Always have status + message
    if not isinstance(result.get("status"), str):
        result["status"] = "ASK"
        result["message"] = result.get("message") or (
            "I need a bit more info to guide you safely. How long has this been going on?"
        )
        result.setdefault("rationale", "missing_status_fallback")

    # Disclaimer: uniform wording
    result["disclaimer"] = result.get("disclaimer") or (
        "Educational guidance only; not a diagnosis; not for emergencies. If this is an emergency, call 112."
    )

    # Categories: ensure SAFE has some (derive from RAG if empty) — never crash
    if result["status"] == "SAFE":
        cats = result.get("categories") or []
        if not cats:
            try:
                docs = rag_search(effective_text, top_n=20, final_k=6)
                cats = _categories_from_docs(docs)
            except Exception as e:
                # Keep going even if retrieval is unavailable
                log_event("categories_rag_error", error=str(e)[:200])
                cats = []
        result["categories"] = cats
    else:
        result.setdefault("categories", [])

    # Other fields always present
    result.setdefault("next_step", "")
    result.setdefault("rationale", "")
    if isinstance(result["rationale"], str):
        result["rationale"] = result["rationale"][:900]

    return result


@router.post("/chat", response_model=ChatOut)
def chat(payload: ChatIn, session_id: str = Query("default")):
    t0 = timer_start()
    safety_action: str | None = None
    request_id = str(uuid.uuid4())  # define before try so except can log it

    try:
        # 1) Session merge + effective text (do not log raw user text)
        sess = get_session(session_id)
        merge_turn(sess, payload.message)
        effective_text = build_effective_text(sess, payload.message)

        # Slot flags for logging / policy
        ctx = {
            "has_age": sess.age is not None,
            "has_severity": sess.severity is not None,
            "has_duration": getattr(sess, "duration_days", None) is not None,
        }
        log_event(
            "triage_request",
            request_id=request_id,
            session_id=session_id,
            asked_slots={"age": ctx["has_age"], "severity": ctx["has_severity"], "duration": ctx["has_duration"]},
        )

        # 2) Extract + reason
        ext = extract(effective_text)
        result = triage(effective_text, ext, ctx=ctx) or {}
        result = _finalize_payload(result, effective_text)

        # 3) Safety self-check (LLM/stub hybrid)
        verdict = safety_review(result, context={"session_id": session_id})
        safety_action = verdict.action

        if verdict.action == "APPROVE":
            pass
        elif verdict.action == "REWRITE":
            # Fill missing disclaimer or safer wording
            if (verdict.reason or "").lower().startswith("missing_disclaimer"):
                result["disclaimer"] = (
                    "Educational guidance only; not a diagnosis; not for emergencies. If this is an emergency, call 112."
                )
            elif verdict.text:
                result["message"] = verdict.text
        elif verdict.action == "BLOCK":
            result = {
                "status": "ASK",
                "message": "For safety, I need more information before I can guide you. Can you describe your symptoms and duration?",
                "categories": [],
                "next_step": "",
                "rationale": "blocked_by_safety_checker",
                "disclaimer": result.get("disclaimer")
                or "Educational guidance only; not a diagnosis; not for emergencies. If this is an emergency, call 112.",
            }

        # Re-finalize in case safety step changed fields
        result = _finalize_payload(result, effective_text)

        # 4) Metrics + logs
        elapsed_ms = timer_observe_ms(t0)
        if safety_action:
            record_safety(safety_action)
        record_status(result.get("status", "ASK"))

        log_event(
            "triage_response",
            request_id=request_id,
            session_id=session_id,
            status=result.get("status", "?"),
            safety_action=safety_action or "N/A",
            elapsed_ms=round(elapsed_ms, 2),
            categories=result.get("categories", []),
        )

        # 5) Return normalized payload
        return ChatOut(
            status=result["status"],
            reply=result["message"],
            categories=result["categories"],
            next_step=result.get("next_step", ""),
            rationale=result.get("rationale", ""),
            disclaimer=result["disclaimer"],
        )

    except Exception as e:
        # Always record timing + error on exceptions
        timer_observe_ms(t0)
        record_error(type(e).__name__)
        log_event(
            "triage_error",
            request_id=request_id,
            session_id=session_id,
            error_type=type(e).__name__,
        )
        raise

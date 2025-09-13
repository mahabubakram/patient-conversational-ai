from fastapi import APIRouter, Query
from pydantic import BaseModel
from app.nlu.extractor import extract
from app.reasoner.triage import triage
from app.safety.disclaimers import DISCLAIMER
from app.storage.memory import get_session, merge_turn, build_effective_text

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

    # 3) Extract + triage on the effective text
    ext = extract(effective_text)
    result = triage(effective_text, ext)

    return ChatOut(
        status=result["status"],
        reply=result["message"],
        categories=result.get("categories", []),
        next_step=result.get("next_step", ""),
        rationale=result.get("rationale", "")[:900],
        disclaimer=result.get("disclaimer", DISCLAIMER),
    )

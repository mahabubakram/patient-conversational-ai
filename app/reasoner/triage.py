from __future__ import annotations

from typing import Any, Dict, List, Tuple, Optional

from app.retrieval.index import search  # new API: search(text, top_n=..., final_k=...)
from app.nlu.schema import ExtractionResult

# If you have the detailed red-flag module, use it; otherwise fallback to simple rules.
try:
    from app.policies.red_flags import check_red_flags_detail
except Exception:
    check_red_flags_detail = None  # type: ignore


# ----------------------------
# Helpers to robustly parse retrieval hits & tags
# ----------------------------

def _normalize_hit(hit: Any) -> Tuple[str, Any]:
    """
    Return (text, meta) from a retrieval hit that might be:
      - {"text":..., "meta": {...}}  (current format)
      - {"document":..., "metadatas": {...}} (alternate)
      - (text, meta) tuple (legacy)
      - plain text (fallback)
    """
    if isinstance(hit, dict):
        text = hit.get("text") or hit.get("document") or ""
        meta = hit.get("meta")
        if meta is None:
            meta = hit.get("metadatas", {})
        return str(text), meta
    if isinstance(hit, (list, tuple)):
        text = hit[0] if len(hit) > 0 else ""
        meta = hit[1] if len(hit) > 1 else {}
        return str(text), meta
    return str(hit), {}


def _meta_to_tags(meta: Any) -> List[str]:
    """
    Accept meta as dict or str. Produce a normalized list of tags.
    - dict: read 'tags' (comma-separated) and optional 'topic'
    - str: treat as comma-separated tags
    """
    tags: List[str] = []
    topic: Optional[str] = None

    if isinstance(meta, dict):
        tags_str = meta.get("tags") or ""
        topic = meta.get("topic")
    elif isinstance(meta, str):
        tags_str = meta
    else:
        tags_str = ""

    for t in (tags_str or "").split(","):
        t = t.strip().lower()
        if t and t not in tags:
            tags.append(t)

    if topic:
        t = str(topic).strip().lower()
        if t and t not in tags:
            tags.append(t)

    return tags


def _collect_categories(hits: List[Any], limit: int = 6) -> List[str]:
    cats: List[str] = []
    for h in hits:
        _, meta = _normalize_hit(h)
        for t in _meta_to_tags(meta):
            if t not in cats:
                cats.append(t)
        if len(cats) >= limit:
            break
    return cats[:limit]


# ----------------------------
# Slot gating (ASK order): duration -> age -> severity
# ----------------------------

def needs_followup(ctx: Dict[str, bool]) -> Optional[str]:
    """
    Returns the next question if required information is missing,
    otherwise None. Enforces order: duration -> age -> severity.
    """
    if not ctx.get("has_duration", False):
        return "How long has this been going on (e.g., hours, days, weeks)?"
    if not ctx.get("has_age", False):
        return "How old are you?"
    if not ctx.get("has_severity", False):
        return "How severe is it (mild, moderate, or severe)?"
    return None


# ----------------------------
# Simple next-step heuristic for SAFE
# ----------------------------

def _parse_severity(text: str) -> Optional[str]:
    t = text.lower()
    if "severe" in t:
        return "severe"
    if "moderate" in t:
        return "moderate"
    if "mild" in t:
        return "mild"
    return None


def _parse_duration_hint(text: str) -> Optional[int]:
    """
    Very light duration parser for fallback heuristics
    (your NLU may already set duration_days in ExtractionResult/session).
    """
    import re
    t = text.lower()
    m = re.search(r"(\d+)\s*(day|days)", t)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*(hour|hours|hr|hrs)", t)
    if m:
        return 0  # treat hours as <1 day
    m = re.search(r"(\d+)\s*(week|weeks|wk|wks)", t)
    if m:
        return int(m.group(1)) * 7
    return None


def _safe_next_step(text: str, ext: ExtractionResult) -> str:
    sev = _parse_severity(text) or getattr(ext, "severity", None) or ""
    days = getattr(ext, "duration_days", None)
    if days is None:
        days = _parse_duration_hint(text)

    # Default routing by severity/duration
    if str(sev).lower() == "severe":
        return "Seek urgent care within 24 hours."
    if str(sev).lower() == "moderate":
        return "Arrange a GP/primary care appointment in the next 24–48 hours."
    # mild:
    if days is not None and days <= 3:
        return "Self-care and monitoring are reasonable; recheck if not improving."
    return "Arrange a GP/primary care appointment."


# ----------------------------
# Fallback red-flag checker (if detailed one is not available)
# ----------------------------

def _basic_red_flags(text: str, ext: ExtractionResult) -> Optional[Dict[str, str]]:
    t = text.lower()

    # Infant fever < 3 months
    if getattr(ext, "age", None) is not None and ext.age < 3 and ("fever" in t or "temperature" in t):
        return {
            "status": "EMERGENCY",
            "message": "Fever in an infant under 3 months is an emergency.",
            "next_step": "Call 112 / go to the emergency department now.",
            "rationale": "infant_fever",
        }

    # Chest pain + shortness of breath
    if ("chest pain" in t or "crushing" in t) and ("shortness of breath" in t or "sob" in t or "trouble breathing" in t):
        return {
            "status": "EMERGENCY",
            "message": "Chest pain with shortness of breath can be an emergency.",
            "next_step": "Call 112 / go to the emergency department now.",
            "rationale": "cardiorespiratory_red_flag",
        }

    # Anaphylaxis
    if ("hives" in t or "swelling" in t) and ("trouble breathing" in t or "shortness of breath" in t):
        return {
            "status": "EMERGENCY",
            "message": "Possible severe allergic reaction.",
            "next_step": "Call 112 / go to the emergency department now.",
            "rationale": "anaphylaxis",
        }

    # Worst headache
    if "worst headache" in t or "thunderclap" in t:
        return {
            "status": "EMERGENCY",
            "message": "A sudden severe (worst) headache can be an emergency.",
            "next_step": "Call 112 / go to the emergency department now.",
            "rationale": "neuro_headache_red_flag",
        }

    # UTI + systemic signs (fever/back pain/flank)
    if ("urination" in t or "urine" in t or "peeing" in t or "burning" in t or "dysuria" in t) and (
        "fever" in t or "back pain" in t or "flank" in t
    ):
        return {
            "status": "URGENT",
            "message": "Urinary symptoms with fever or back pain may indicate kidney involvement.",
            "next_step": "Seek urgent care or same-day GP evaluation.",
            "rationale": "uti_systemic",
        }

    return None


# ----------------------------
# Main triage entry point
# ----------------------------

def triage(text: str, ext: ExtractionResult, ctx: Dict[str, bool]) -> Dict[str, Any]:
    """
    Returns a dict (may be partial); the API layer will finalize and run safety check.

    Keys we try to set:
      - status: "ASK" | "SAFE" | "URGENT" | "EMERGENCY"
      - message: short assistant-facing text (no diagnosis claims)
      - categories: list[str] (optional; API will derive if missing)
      - next_step: short recommendation string
      - rationale: internal code for why this path was chosen
    """

    # 0) Red flags first (use detailed checker if available)
    if check_red_flags_detail:
        hit = check_red_flags_detail(text, ext)
        if hit:
            # Ensure a consistent shape
            return {
                "status": hit.get("status", "EMERGENCY"),
                "message": hit.get("message", "This may be an emergency."),
                "categories": [],
                "next_step": hit.get("next_step", "Call 112 / go to the emergency department."),
                "rationale": hit.get("rationale", "red_flag"),
            }
    else:
        hit = _basic_red_flags(text, ext)
        if hit:
            return hit

    # 1) Strict slot gating (ASK order)
    q = needs_followup(ctx)
    if q:
        return {
            "status": "ASK",
            "message": q,
            "categories": [],
            "next_step": "",
            "rationale": "missing_required_slots",
        }

    # 2) Retrieve supportive snippets (defensive: never crash)
    docs: List[Dict[str, Any]] = []
    try:
        docs = search(text, top_n=20, final_k=4)  # diverse but focused set
    except Exception:
        docs = []

    cats = _collect_categories(docs, limit=6)

    # 3) Compose SAFE guidance (non-diagnostic)
    msg = "Based on what you shared, this sounds suitable for initial self-care and monitoring."
    step = _safe_next_step(text, ext)

    # Slight tweak if clearly urinary / cough etc., purely for UX tone (non-diagnostic)
    t = text.lower()
    if any(k in t for k in ("urination", "peeing", "dysuria", "burning when peeing")):
        msg = "Your urinary symptoms can often be monitored initially if mild and short-lived."
    elif any(k in t for k in ("cough", "sore throat", "cold", "upper respiratory")):
        msg = "Upper-respiratory symptoms are commonly mild and self-limited if no red flags."

    return {
        "status": "SAFE",
        "message": msg,
        "categories": cats,      # API will fill if empty
        "next_step": step,
        "rationale": "safe_guidance",
        # disclaimer is added uniformly by the API layer
    }

from typing import List, Optional, Dict
from pydantic import BaseModel

class Entity(BaseModel):
    type: str      # spaCy’s label (e.g., ORG, GPE, etc.) for now
    text: str      # the surface span
    negated: bool = False
    start: int     # char offset
    end: int

class ExtractionResult(BaseModel):
    age: Optional[int] = None
    pregnant: Optional[bool] = None
    entities: List[Entity] = []
    meta: Dict[str, str] = {}
    duration_days: Optional[float] = None
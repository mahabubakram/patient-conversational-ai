# app/retrieval/index.py
from __future__ import annotations
import os
from typing import List, Dict, Any, Tuple
import numpy as np
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

from app.observability.metrics import record_retrieval, record_mmr
from app.retrieval.rank import expand_query, mmr_select

os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
os.environ.setdefault("CHROMA_TELEMETRY_ENABLED", "false")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CHROMA_DIR = os.path.join(REPO_ROOT, ".chroma")

PREFERRED_COLLECTIONS = ("carepaths_v2", "carepaths")
EMBED_MODEL_NAME = os.getenv("EMBED_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")

_client = None
_model = None
_coll = None

def _client_lazy():
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=CHROMA_DIR, settings=Settings(allow_reset=True, anonymized_telemetry=False))
    return _client

def _get_collection():
    global _coll
    if _coll is not None:
        return _coll
    client = _client_lazy()
    for name in PREFERRED_COLLECTIONS:
        try:
            _coll = client.get_collection(name)
            return _coll
        except Exception:
            continue
    raise RuntimeError("No retrieval collection found. Run ingestion first.")

def _embedder_lazy():
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBED_MODEL_NAME)
    return _model
# K number of results: Top K
def search(query_text: str, top_n: int = 20, final_k: int = 4) -> List[Dict[str, Any]]:
    """
    Return a list of up to final_k dicts: {id, text, meta}
    with MMR re-ranking over a widened candidate pool.
    """
    coll = _get_collection()
    expansions = expand_query(query_text)  # [original + aliases]

    # Gather candidates from each expansion
    # Ask Chroma to return embeddings so we can run MMR locally
    seen = {}
    for q in expansions:
        res = coll.query(
            query_texts=[q],
            n_results=top_n,
            include=["documents", "metadatas", "embeddings"],
        )
        ids = res.get("ids")[0]
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        embs = res.get("embeddings", [[]])[0]  # list of vectors

        for i, _id in enumerate(ids):
            if _id not in seen:
                seen[_id] = {
                    "id": _id,
                    "text": docs[i],
                    "meta": metas[i] or {},
                    "vec": np.array(embs[i], dtype=np.float32),
                }

    candidates = list(seen.values())
    if not candidates:
        record_retrieval(False)
        return []

    record_retrieval(True)

    # Build query embedding with the same model used in ingest
    model = _embedder_lazy()
    qvec = model.encode([query_text], normalize_embeddings=True)[0]
    dmat = np.vstack([c["vec"] for c in candidates])

    # Apply MMR to get diverse top-k
    idxs = mmr_select(np.array(qvec, dtype=np.float32), dmat, k=final_k, lambda_mult=0.9) # how similar it is: 0.9
    record_mmr()

    selected = [candidates[i] for i in idxs]
    # Strip vectors from output
    return [{"id": s["id"], "text": s["text"], "meta": s["meta"]} for s in selected]

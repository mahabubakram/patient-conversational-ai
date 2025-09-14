# app/retrieval/rank.py
from __future__ import annotations
from typing import List, Sequence, Tuple
import numpy as np

# Lightweight synonym/alias expansion.
# Keep it tiny and explicit; we can grow it later.
QUERY_ALIASES = {
    "sob": ["shortness of breath", "breathless", "trouble breathing"],
    "short of breath": ["shortness of breath", "sob"],
    "dysuria": ["burning urination", "painful urination"],
    "burning when peeing": ["burning urination", "painful urination", "dysuria"],
    "uti": ["urinary tract infection", "urinary symptoms", "dysuria"],
    "mi": ["heart attack", "chest pain"],
    "worst headache": ["thunderclap headache", "sudden severe headache"],
}

def expand_query(q: str) -> List[str]:
    """Return [original + expansions], unique, lowercased."""
    ql = q.strip().lower()
    out = [ql]
    for key, exps in QUERY_ALIASES.items():
        if key in ql:
            out.extend(exps)
    # tiny normalization
    out = list(dict.fromkeys([s.strip().lower() for s in out if s.strip()]))
    return out

def _cosine_sim_matrix(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    # Normalize to unit vectors, then dot
    A = A / (np.linalg.norm(A, axis=1, keepdims=True) + 1e-12)
    B = B / (np.linalg.norm(B, axis=1, keepdims=True) + 1e-12)
    return A @ B.T

def mmr_select(
    query_vec: np.ndarray,
    doc_vecs: np.ndarray,
    k: int,
    lambda_mult: float = 0.7,
) -> List[int]:
    """
    Max Marginal Relevance selection indices.
    - query_vec: (d,)
    - doc_vecs: (n, d)
    Returns indices of selected docs (len <= k).
    """
    n = doc_vecs.shape[0]
    if n == 0:
        return []
    k = min(k, n)

    # Similarity to query
    qsim = _cosine_sim_matrix(doc_vecs, query_vec.reshape(1, -1)).flatten()

    selected: List[int] = []
    candidate_idxs = list(range(n))

    # Precompute doc-doc similarity for diversity term
    dsim = _cosine_sim_matrix(doc_vecs, doc_vecs)

    while candidate_idxs and len(selected) < k:
        if not selected:
            # pick best by query similarity
            best = max(candidate_idxs, key=lambda i: qsim[i])
            selected.append(best)
            candidate_idxs.remove(best)
            continue

        def mmr_score(i: int) -> float:
            diversity = max(dsim[i, s] for s in selected) if selected else 0.0
            return lambda_mult * qsim[i] - (1.0 - lambda_mult) * diversity

        best = max(candidate_idxs, key=mmr_score)
        selected.append(best)
        candidate_idxs.remove(best)

    return selected

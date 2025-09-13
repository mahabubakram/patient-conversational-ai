import os, glob, yaml
from dataclasses import dataclass
from typing import List, Tuple
import chromadb
from chromadb.utils import embedding_functions

EMBED_MODEL = "all-MiniLM-L6-v2"  # SentenceTransformers model


import os
os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
os.environ.setdefault("CHROMA_TELEMETRY_ENABLED", "false")


@dataclass
class Snippet:
    id: str
    text: str
    tags: List[str]
    urgency: str

def _parse_md(path: str) -> Snippet:
    with open(path, "r", encoding="utf-8") as f:
        content = f.read().strip()
    if content.startswith("---"):
        try:
            _, fm, body = content.split("---", 2)
            meta = yaml.safe_load(fm) or {}
            return Snippet(
                id=meta.get("id") or os.path.basename(path),
                text=body.strip(),
                tags=meta.get("tags", []),
                urgency=str(meta.get("urgency", "unknown")),
            )
        except Exception:
            pass
    return Snippet(id=os.path.basename(path), text=content, tags=[], urgency="unknown")

def build_or_load_index(care_paths_dir: str = "care_paths"):
    client = chromadb.PersistentClient(path=".chroma")
    coll = client.get_or_create_collection(
        name="care_paths",
        embedding_function=embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=EMBED_MODEL
        ),
    )
    if coll.count() == 0:
        docs, ids, metas = [], [], []
        for p in glob.glob(os.path.join(care_paths_dir, "*.md")):
            s = _parse_md(p)
            docs.append(s.text)
            ids.append(s.id)
            # Chroma metadata must be primitives; store tags as a comma-separated string
            metas.append({"tags": ",".join(s.tags), "urgency": s.urgency, "path": p})
        if ids:
            coll.add(documents=docs, ids=ids, metadatas=metas)
    return coll

def search(query: str, top_k: int = 3) -> List[Tuple[str, str, dict]]:
    coll = build_or_load_index()
    res = coll.query(query_texts=[query], n_results=top_k)
    print(f"results length: {len(res)}")
    results: List[Tuple[str, str, dict]] = []
    for i in range(len(res["ids"][0])):
        results.append((
            res["ids"][0][i],
            res["documents"][0][i],
            res["metadatas"][0][i],
        ))
        print(f"{results[i]}\n")
    return results

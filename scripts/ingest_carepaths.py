#!/usr/bin/env python3
"""
Ingest care_paths/*.md -> chunks -> embeddings -> Chroma collection.

Usage:
  python scripts/ingest_carepaths.py --rebuild
  python scripts/ingest_carepaths.py --dry-run

Notes:
- Metadata values must be str/int/float/bool (no lists), so 'tags' is a comma-separated str.
- Deterministic IDs: <topic>-<chunk_index:03d>
"""

import argparse
import glob
import os
import re
from dataclasses import dataclass
from typing import List, Tuple

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CARE_DIR = os.path.join(REPO_ROOT, "care_paths")
CHROMA_DIR = os.path.join(REPO_ROOT, ".chroma")
COLLECTION_NAME = "carepaths_v2"

EMBED_MODEL_NAME = os.getenv("EMBED_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")

# --- tiny topic->tags heuristic (string, not list!)
TOPIC_TAGS = {
    "cough": "cough,upper_respiratory,self_care",
    "sore_throat": "sore_throat,upper_respiratory,self_care",
    "headache": "headache,neurologic,self_care",
    "abdominal_pain": "abdominal,gi,triage",
    "urinary_symptoms": "urinary,dysuria,uti",
}

@dataclass
class Chunk:
    doc_id: str         # deterministic: <topic>-<idx:03d>
    text: str           # content
    source: str         # file path
    topic: str          # topic (from filename)
    idx: int            # chunk index (0..N-1)
    tags: str           # comma-separated tags

def _read_markdown(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def _split_blocks(md: str) -> List[str]:
    # Split on headings and blank lines into coarse blocks
    blocks = re.split(r"\n\s*\n", md.strip())
    blocks = [b.strip() for b in blocks if b.strip()]
    return blocks

def _sentence_split(text: str) -> List[str]:
    # Lightweight sentence-ish split to avoid spaCy dependency here
    parts = re.split(r"(?<=[\.\!\?])\s+(?=[A-Z0-9])", text.strip())
    return [p.strip() for p in parts if p.strip()]

def _chunk_block(text: str, max_chars: int = 700) -> List[str]:
    # Pack sentences into ~max_chars chunks
    sents = _sentence_split(text)
    chunks, buf = [], ""
    for s in sents:
        if not buf:
            buf = s
            continue
        if len(buf) + 1 + len(s) <= max_chars:
            buf = f"{buf} {s}"
        else:
            chunks.append(buf)
            buf = s
    if buf:
        chunks.append(buf)
    return chunks

def _topic_from_path(path: str) -> str:
    name = os.path.splitext(os.path.basename(path))[0]
    # normalize typical file names: "sore_throat" etc.
    return name.lower()

def _chunk_markdown(path: str) -> List[str]:
    md = _read_markdown(path)
    blocks = _split_blocks(md)
    all_chunks: List[str] = []
    for b in blocks:
        all_chunks.extend(_chunk_block(b, max_chars=700))
    # De-dup trivial repeats
    uniq = []
    seen = set()
    for c in all_chunks:
        k = c.strip()
        if k not in seen:
            uniq.append(k)
            seen.add(k)
    return uniq

def build_chunks() -> List[Chunk]:
    paths = sorted(glob.glob(os.path.join(CARE_DIR, "*.md")))
    chunks: List[Chunk] = []
    for path in paths:
        topic = _topic_from_path(path)
        tags = TOPIC_TAGS.get(topic, topic)
        texts = _chunk_markdown(path)
        for i, txt in enumerate(texts):
            doc_id = f"{topic}-{i:03d}"
            chunks.append(Chunk(
                doc_id=doc_id,
                text=txt,
                source=os.path.relpath(path, REPO_ROOT),
                topic=topic,
                idx=i,
                tags=tags,
            ))
    return chunks

def ensure_collection(client) -> chromadb.api.models.Collection.Collection:
    try:
        return client.get_collection(COLLECTION_NAME)
    except Exception:
        return client.create_collection(COLLECTION_NAME)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true", help="Drop and rebuild collection")
    ap.add_argument("--dry-run", action="store_true", help="Show planned chunks & exit")
    args = ap.parse_args()

    chunks = build_chunks()
    print(f"Found {len(chunks)} chunks from {CARE_DIR}")

    if args.dry_run:
        for c in chunks[:6]:
            print(f"- {c.doc_id} [{c.topic}] tags={c.tags} :: {c.text[:90]!r}...")
        if len(chunks) > 6:
            print(f"... {len(chunks)-6} more")
        return

    client = chromadb.PersistentClient(path=CHROMA_DIR, settings=Settings(allow_reset=True, anonymized_telemetry=False))
    if args.rebuild:
        try:
            client.delete_collection(COLLECTION_NAME)
            print(f"Deleted existing collection '{COLLECTION_NAME}'")
        except Exception:
            pass

    coll = ensure_collection(client)

    # Embed in batches
    print(f"Loading embedding model: {EMBED_MODEL_NAME}")
    model = SentenceTransformer(EMBED_MODEL_NAME)

    BATCH = 64
    ids, docs, metas = [], [], []

    def flush():
        if not ids:
            return
        vecs = model.encode(docs, normalize_embeddings=True).tolist()
        coll.add(
            ids=list(ids),
            documents=list(docs),
            metadatas=list(metas),  # only str/int/float/bool values
            embeddings=vecs,  # ← store vectors in Chroma
        )
        ids.clear(); docs.clear(); metas.clear()

    for c in chunks:
        ids.append(c.doc_id)
        docs.append(c.text)
        metas.append({
            "topic": c.topic,
            "source": c.source,
            "chunk_index": c.idx,
            "tags": c.tags,   # comma-delimited string (NOT a list)
        })
        if len(ids) >= BATCH:
            # Let Chroma do the embeddings via the client’s embedding function OR precompute:
            # Precompute option (uncomment if you wired a manual embedding function):
            # vecs = model.encode(docs, normalize_embeddings=True).tolist()
            # coll.add(ids=..., documents=..., metadatas=..., embeddings=vecs)
            flush()

    flush()
    print(f"Ingested {len(chunks)} chunks into collection '{COLLECTION_NAME}' at {CHROMA_DIR}")

if __name__ == "__main__":
    main()

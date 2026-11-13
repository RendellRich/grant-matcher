"""Semantic embeddings for grants, foundations and state programs (built offline) and for a
mission (built in the app). Uses a small ONNX model through fastembed, so no GPU or PyTorch is needed.

Run:
  python -m grantmatch.embed federal data/opportunities.json.gz data/embeddings.npz
  python -m grantmatch.embed florida data/florida.json.gz data/florida.npz
  python -m grantmatch.embed foundations data/foundations/FL.json.gz data/foundations/FL.npz
"""
from __future__ import annotations

import gzip
import json
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np

MODEL = "BAAI/bge-small-en-v1.5"


@lru_cache(maxsize=1)
def _model():
    from fastembed import TextEmbedding
    return TextEmbedding(MODEL)


def doc_text(rec: dict) -> str:
    cats = ", ".join(rec.get("category_labels") or [])
    return f"{rec['title']}. {cats}. {rec['description'][:1800]}"


def embed_texts(texts: list[str]) -> np.ndarray:
    vecs = np.array(list(_model().passage_embed(texts, batch_size=64)), dtype=np.float32)
    return vecs / np.linalg.norm(vecs, axis=1, keepdims=True)


def embed_docs(records: list[dict]) -> np.ndarray:
    return embed_texts([doc_text(r) for r in records])


def embed_query(text: str) -> np.ndarray:
    vec = np.array(list(_model().query_embed([text]))[0], dtype=np.float32)
    return vec / np.linalg.norm(vec)


def save(ids: list[str], vecs: np.ndarray, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, ids=np.array(ids), vecs=vecs.astype(np.float16), model=np.array(MODEL))


def load(path) -> dict[str, np.ndarray]:
    data = np.load(path, allow_pickle=False)
    return dict(zip(data["ids"].tolist(), data["vecs"].astype(np.float32)))


def main() -> None:
    from .rank_more import florida_doc, foundation_doc

    kind, src, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    payload = json.load(gzip.open(src, "rt", encoding="utf-8"))
    limit = 2000
    if kind == "federal":
        records, key, doc = payload["opportunities"], "id", doc_text
    elif kind == "florida":
        records, key, doc = payload["programs"], "id", florida_doc
    elif kind == "foundations":
        records, key, doc, limit = payload["foundations"], "ein", foundation_doc, 1000
    else:
        raise SystemExit(f"unknown kind {kind}")
    vecs = embed_texts([doc(r)[:limit] for r in records])
    save([r[key] for r in records], vecs, out)
    print(f"wrote {len(records)} embeddings to {out}")


if __name__ == "__main__":
    main()

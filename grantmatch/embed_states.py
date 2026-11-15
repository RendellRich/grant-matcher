"""Embeddings for the foundation state files, built once per foundation and kept between runs.

A foundation sits in the file of its own state and of every state it gives to, so embedding each state
file on its own repeats the same work many times over (the first full run timed out after five hours).
Here every distinct document is embedded once, keyed by a hash of its text, and the vectors are kept in
a cache that the next run reuses, so a monthly refresh only embeds foundations whose returns changed.

  shard: embed this shard's share of the documents the cache doesn't have yet
    python -m grantmatch.embed_states shard --cache cache.npz --index 0 --count 8 --out part-0.npz DIR [DIR ...]
  split: merge the cache and the shards, then write one .npz per state file next to it
    python -m grantmatch.embed_states split --cache cache.npz --out-cache new-cache.npz DIR [DIR ...] --parts part-*.npz
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np

from . import embed
from .rank_more import foundation_doc

DOC_LIMIT = 1000  # same cut as embed.main uses for foundations


def doc_of(rec: dict) -> str:
    return foundation_doc(rec)[:DOC_LIMIT]


def doc_hash(text: str) -> str:
    return hashlib.sha1(f"{embed.MODEL}\n{text}".encode("utf-8")).hexdigest()


def state_files(dirs: list[Path]) -> list[Path]:
    return sorted(p for d in dirs for p in d.glob("*.json.gz"))


def records(path: Path) -> list[dict]:
    return json.load(gzip.open(path, "rt", encoding="utf-8"))["foundations"]


def load_cache(path: Path | None) -> dict[str, np.ndarray]:
    """Hash -> vector. A missing or unreadable cache just means everything is embedded again."""
    if not path or not path.exists():
        return {}
    try:
        data = np.load(path, allow_pickle=False)
        if str(data["model"]) != embed.MODEL:
            return {}
        return dict(zip(data["hashes"].tolist(), data["vecs"]))
    except Exception:
        return {}


def save_cache(cache: dict[str, np.ndarray], path: Path) -> None:
    keys = sorted(cache)
    vecs = np.stack([cache[k] for k in keys]).astype(np.float16) if keys else np.zeros((0, 384), np.float16)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, hashes=np.array(keys), vecs=vecs, model=np.array(embed.MODEL))


def missing_docs(dirs: list[Path], cache: dict[str, np.ndarray]) -> dict[str, str]:
    """Every distinct document across the state files that the cache doesn't have, by hash."""
    todo: dict[str, str] = {}
    for path in state_files(dirs):
        for rec in records(path):
            text = doc_of(rec)
            h = doc_hash(text)
            if h not in cache:
                todo[h] = text
    return todo


def shard(dirs: list[Path], cache_path: Path | None, index: int, count: int, out: Path) -> int:
    todo = missing_docs(dirs, load_cache(cache_path))
    mine = [h for i, h in enumerate(sorted(todo)) if i % count == index]
    vecs = embed.embed_texts([todo[h] for h in mine]) if mine else np.zeros((0, 384), np.float32)
    save_cache(dict(zip(mine, vecs)), out)
    print(f"shard {index + 1} of {count}: {len(todo)} new documents in all, embedded {len(mine)} into {out}", flush=True)
    return len(mine)


def split(dirs: list[Path], cache_path: Path | None, parts: list[Path], out_cache: Path) -> None:
    cache = load_cache(cache_path)
    for part in parts:
        cache.update(load_cache(part))
    used: dict[str, np.ndarray] = {}
    files = state_files(dirs)
    for path in files:
        ids, vecs = [], []
        for rec in records(path):
            h = doc_hash(doc_of(rec))
            if h not in cache:
                raise SystemExit(f"{path.name}: no vector for {rec['ein']}; a shard is missing")
            ids.append(rec["ein"])
            vecs.append(cache[h])
            used[h] = cache[h]
        stacked = np.stack(vecs).astype(np.float32) if vecs else np.zeros((0, 384), np.float32)
        embed.save(ids, stacked, path.with_name(path.name.replace(".json.gz", ".npz")))
    # Keep only what this month's files use, so the cache doesn't grow with closed foundations.
    save_cache(used, out_cache)
    print(f"wrote {len(files)} state vector files; cache holds {len(used)} documents", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("shard")
    a.add_argument("dirs", nargs="+", type=Path)
    a.add_argument("--cache", type=Path)
    a.add_argument("--index", type=int, required=True)
    a.add_argument("--count", type=int, required=True)
    a.add_argument("--out", type=Path, required=True)
    b = sub.add_parser("split")
    b.add_argument("dirs", nargs="+", type=Path)
    b.add_argument("--cache", type=Path)
    b.add_argument("--parts", nargs="*", type=Path, default=[])
    b.add_argument("--out-cache", type=Path, required=True)
    args = ap.parse_args()
    if args.cmd == "shard":
        shard(args.dirs, args.cache, args.index, args.count, args.out)
    else:
        split(args.dirs, args.cache, args.parts, args.out_cache)


if __name__ == "__main__":
    main()

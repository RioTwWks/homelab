#!/usr/bin/env python3
"""Semantic search smoke test for homelab_knowledge collection."""

from __future__ import annotations

import argparse
import hashlib
import math
import os
import struct

import httpx
from qdrant_client import QdrantClient


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


def _fake_embed(text: str, size: int = 768) -> list[float]:
    digest = hashlib.sha256(text.encode()).digest()
    out: list[float] = []
    while len(out) < size:
        for i in range(0, len(digest), 4):
            chunk = digest[i : i + 4]
            if len(chunk) < 4:
                chunk = chunk.ljust(4, b"\0")
            val = struct.unpack(">I", chunk)[0] / 2**32
            out.append(val * 2.0 - 1.0)
            if len(out) >= size:
                break
        digest = hashlib.sha256(digest).digest()
    norm = math.sqrt(sum(x * x for x in out)) or 1.0
    return [x / norm for x in out]


def embed_query(client: httpx.Client, model: str, query: str) -> list[float]:
    resp = client.post("/api/embeddings", json={"model": model, "prompt": query}, timeout=120.0)
    resp.raise_for_status()
    emb = resp.json().get("embedding")
    if not isinstance(emb, list):
        raise RuntimeError(resp.text)
    return [float(x) for x in emb]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--fake-embeddings", action="store_true")
    args = parser.parse_args()

    qdrant_url = _env("QDRANT_URL", "http://localhost:6333")
    collection = _env("QDRANT_COLLECTION", "homelab_knowledge")
    ollama_base = _env("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    embed_model = _env("OLLAMA_EMBED_MODEL", "nomic-embed-text")

    if args.fake_embeddings:
        vector = _fake_embed(args.query)
    else:
        with httpx.Client(base_url=ollama_base) as http:
            vector = embed_query(http, embed_model, args.query)

    hits = QdrantClient(url=qdrant_url).search(collection_name=collection, query_vector=vector, limit=args.top_k)
    if not hits:
        print("[rag] no results")
        return 1
    for i, hit in enumerate(hits, 1):
        path = hit.payload.get("path", "?")
        text = (hit.payload.get("text") or "")[:200].replace("\n", " ")
        print(f"{i}. score={hit.score:.4f} {path}\n   {text}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

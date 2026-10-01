#!/usr/bin/env python3
"""Index homelab docs and code into Qdrant (Ollama embeddings or --fake-embeddings)."""

from __future__ import annotations

import argparse
import hashlib
import math
import os
import struct
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INCLUDE_DIRS = ("docs", "moltbot_api/app", "media_api/app", "scripts")
DEFAULT_ROOT_FILES = ("README.md", "AGENTS.md")
DEFAULT_EXTENSIONS = {".md", ".py", ".sh", ".yml", ".yaml", ".toml", ".json"}
DEFAULT_EXCLUDE_DIR_NAMES = {
    ".git", ".venv", "venv", "__pycache__", "node_modules", "dist", "build",
    ".pytest_cache", ".cursor", "tests",
}


@dataclass(frozen=True)
class Chunk:
    text: str
    path: str
    chunk_index: int
    source_type: str


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


def iter_source_files(
    repo_root: Path,
    include_dirs: tuple[str, ...],
    root_files: tuple[str, ...],
    extensions: set[str],
    exclude_dir_names: set[str],
    max_files: int,
) -> Iterator[Path]:
    count = 0
    for name in root_files:
        path = repo_root / name
        if path.is_file():
            yield path
            count += 1
            if count >= max_files:
                return
    for rel in include_dirs:
        base = repo_root / rel
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            if any(part in exclude_dir_names for part in path.parts):
                continue
            if path.suffix.lower() not in extensions:
                continue
            yield path
            count += 1
            if count >= max_files:
                return


def chunk_text(text: str, chunk_chars: int, overlap: int) -> list[str]:
    text = text.replace("\r\n", "\n").strip()
    if not text:
        return []
    if len(text) <= chunk_chars:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_chars)
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return chunks


def source_type_for(path: Path, repo_root: Path) -> str:
    rel = path.relative_to(repo_root).as_posix()
    if rel.startswith("docs/"):
        return "documentation"
    if rel.endswith(".py"):
        return "code"
    if rel.endswith(".sh"):
        return "script"
    return "repo"


def build_chunks(repo_root: Path, files: Iterable[Path], chunk_chars: int, overlap: int) -> list[Chunk]:
    out: list[Chunk] = []
    for path in files:
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print(f"[skip] {path}: {exc}", file=sys.stderr)
            continue
        rel = path.relative_to(repo_root).as_posix()
        st = source_type_for(path, repo_root)
        for idx, piece in enumerate(chunk_text(raw, chunk_chars, overlap)):
            out.append(Chunk(text=piece, path=rel, chunk_index=idx, source_type=st))
    return out


def point_id(rel_path: str, chunk_index: int) -> str:
    digest = hashlib.sha256(f"{rel_path}:{chunk_index}".encode()).hexdigest()
    return str(uuid.UUID(digest[:32]))


def fake_embed(text: str, size: int = 768) -> list[float]:
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


def ollama_embed(client: httpx.Client, model: str, texts: list[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for text in texts:
        resp = client.post("/api/embeddings", json={"model": model, "prompt": text}, timeout=120.0)
        resp.raise_for_status()
        emb = resp.json().get("embedding")
        if not isinstance(emb, list):
            raise RuntimeError(f"Unexpected Ollama embeddings response: {resp.text}")
        vectors.append([float(x) for x in emb])
    return vectors


def ensure_collection(client: QdrantClient, name: str, vector_size: int, recreate: bool) -> None:
    names = {c.name for c in client.get_collections().collections}
    if name in names:
        if recreate:
            client.delete_collection(name)
        else:
            info = client.get_collection(name)
            params = info.config.params.vectors
            if params is not None and params.size != vector_size:
                raise SystemExit(
                    f"Collection {name!r} size {params.size} != {vector_size}; use --recreate-collection."
                )
            return
    client.create_collection(
        collection_name=name,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )


def upsert_chunks(
    qdrant: QdrantClient,
    collection: str,
    chunks: list[Chunk],
    vectors: list[list[float]],
    batch_size: int,
) -> None:
    points = [
        PointStruct(
            id=point_id(c.path, c.chunk_index),
            vector=v,
            payload={"text": c.text, "path": c.path, "chunk_index": c.chunk_index, "source_type": c.source_type},
        )
        for c, v in zip(chunks, vectors, strict=True)
    ]
    for i in range(0, len(points), batch_size):
        qdrant.upsert(collection_name=collection, points=points[i : i + batch_size])


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest homelab docs/code into Qdrant.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--recreate-collection", action="store_true")
    parser.add_argument("--fake-embeddings", action="store_true")
    parser.add_argument("--max-files", type=int, default=int(_env("RAG_MAX_FILES", "2000")))
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--limit-chunks", type=int, default=0)
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    qdrant_url = _env("QDRANT_URL", "http://localhost:6333")
    collection = _env("QDRANT_COLLECTION", "homelab_knowledge")
    ollama_base = _env("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    embed_model = _env("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    chunk_chars = int(_env("RAG_CHUNK_CHARS", "1200"))
    overlap = int(_env("RAG_CHUNK_OVERLAP", "200"))

    files = list(
        iter_source_files(
            repo_root, DEFAULT_INCLUDE_DIRS, DEFAULT_ROOT_FILES,
            DEFAULT_EXTENSIONS, DEFAULT_EXCLUDE_DIR_NAMES, args.max_files,
        )
    )
    chunks = build_chunks(repo_root, files, chunk_chars, overlap)
    if args.limit_chunks > 0:
        chunks = chunks[: args.limit_chunks]

    print(f"[rag] repo={repo_root} files={len(files)} chunks={len(chunks)} collection={collection!r}")
    if args.dry_run:
        for c in chunks[:15]:
            print(f"  {c.path}#{c.chunk_index}: {c.text[:70].replace(chr(10), ' ')}…")
        if len(chunks) > 15:
            print(f"  … {len(chunks) - 15} more")
        return 0
    if not chunks:
        return 1

    qdrant = QdrantClient(url=qdrant_url)
    if args.fake_embeddings:
        ensure_collection(qdrant, collection, 768, args.recreate_collection)
        upsert_chunks(qdrant, collection, chunks, [fake_embed(c.text) for c in chunks], 64)
        print(f"[rag] upserted {len(chunks)} points (fake embeddings)")
        return 0

    with httpx.Client(base_url=ollama_base) as http:
        probe = ollama_embed(http, embed_model, [chunks[0].text])
        size = len(probe[0])
        ensure_collection(qdrant, collection, size, args.recreate_collection)
        embedded = list(probe)
        bs = max(1, args.batch_size)
        for i in range(1, len(chunks), bs):
            batch = chunks[i : i + bs]
            embedded.extend(ollama_embed(http, embed_model, [c.text for c in batch]))
        upsert_chunks(qdrant, collection, chunks, embedded, 64)
        print(f"[rag] upserted {len(chunks)} points via Ollama {embed_model!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# RAG на Qdrant (homelab + Hermes)

Qdrant входит в базовый `docker compose`. Индексация — **на хосте** через `scripts/rag/` (эмбеддинги Ollama). Hermes подключается к тому же Qdrant по HTTP; шаблон: [`templates/hermes-rag.yaml`](./templates/hermes-rag.yaml).

## Быстрый старт

```bash
docker compose up -d qdrant
curl -s http://localhost:6333/healthz
ollama pull nomic-embed-text

./scripts/rag/ingest.sh --dry-run
./scripts/rag/ingest.sh
.venv-rag/bin/python scripts/rag/search_homelab.py "профиль storage docker compose"
```

Коллекция: **`homelab_knowledge`**. Индекс: `docs/`, `moltbot_api/app/`, `media_api/app/`, `scripts/`, `README.md`, `AGENTS.md`.

## Переменные

| Переменная | Default |
|------------|---------|
| `QDRANT_URL` | `http://localhost:6333` |
| `QDRANT_COLLECTION` | `homelab_knowledge` |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` |

См. `.env.example`.

## Smoke test без Ollama

```bash
./scripts/rag/ingest.sh --fake-embeddings --recreate-collection --limit-chunks 50
.venv-rag/bin/python scripts/rag/search_homelab.py --fake-embeddings "docker compose"
```

## Hermes

1. [Qdrant memory plugin](https://github.com/qdrant-labs/hermes-agent-memory-qdrant) + фрагмент `docs/templates/hermes-rag.yaml` → `~/.hermes/config.yaml`.
2. Блок из плана (фаза 6):

```yaml
rag:
  provider: qdrant
  url: http://localhost:6333
  collection: homelab_knowledge
```

3. После `./scripts/rag/ingest.sh` задайте вопрос по `docs/install.md`.

## Rollback

`curl -X DELETE "http://localhost:6333/collections/homelab_knowledge"` — см. `docs/backup.md` для тома `qdrant_data`.

# Режимы AI / Gaming / Media

Переключение: **moltbot-ui** → `POST /v1/system/homelab-mode` → `runtime/homelab-mode/state.json` → executor `:8092` → `homelab_mode.sh`.

| Режим | Ollama | Использование |
|-------|--------|----------------|
| AI | on | LLM, голос |
| Gaming | off | Steam/Proton |
| Media | on | Kodi, Stremio |

`HOMELAB_MODE_EXECUTOR_URL=http://host.docker.internal:8092`

**Gaming:** Ollama останавливается; запускайте Steam (`steam -bigpicture`). После игры — AI/Media.

Systemd: `scripts/systemd/homelab-mode-executor.service`, `homelab-mode-sync.path`.

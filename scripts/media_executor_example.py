#!/usr/bin/env python3
"""
Минимальный Media Executor для теста: принимает POST с командой от media-api,
по open_url открывает URL в системном браузере. Остальные action можно добавить
(playerctl, Kodi JSON-RPC и т.д.).

Запуск на хосте: python scripts/media_executor_example.py
Порт по умолчанию 8091. В .env задать MEDIA_EXECUTOR_URL=http://host.docker.internal:8091
"""
import json
import sys
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = 8091


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print("[media-executor]", format % args)

    def do_POST(self):
        if self.path != "/" and not self.path.startswith("/run"):
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            cmd = json.loads(body)
        except Exception as e:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode())
            return
        action = cmd.get("action", "")
        result = {"ok": True, "action": action}
        if action == "open_url" and cmd.get("url"):
            webbrowser.open(cmd["url"])
            result["opened"] = cmd["url"]
        # play/pause/next/prev/volume_* — здесь: playerctl, Kodi JSON-RPC и т.д.
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())


def main():
    print(f"Media executor listening on 0.0.0.0:{PORT}")
    print("Set MEDIA_EXECUTOR_URL=http://host.docker.internal:8091 for media-api")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
    sys.exit(0)

#!/usr/bin/env python3
"""
Media Executor для kiosk-режима: один Chromium на весь экран, по команде open_url
переход на нужный URL через Chrome DevTools Protocol (CDP).

Запуск на хосте:
  pip install websocket-client   # один раз
  python scripts/media_executor_kiosk.py

Опционально в .env (или перед запуском):
  MEDIA_KIOSK_CHROMIUM=google-chrome   # или chromium, chromium-browser, yandex-browser
  MEDIA_KIOSK_CDP_PORT=9222
  MEDIA_KIOSK_NO_LAUNCH=1              # не запускать браузер самим (уже запущен с --remote-debugging-port=9222)
  MEDIA_KIOSK_USER_DATA_DIR=~/.cache/media-kiosk-browser  # отдельный профиль
  KODI_URL=http://127.0.0.1:8080   # Kodi JSON-RPC (включи «удалённое управление по HTTP» в Kodi)
  KODI_LAUNCH_CMD=kodi             # команда запуска по «включи коди» (опционально)
"""
import json
import os
import subprocess
import sys
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError


def _load_env_from_project_root() -> None:
    """Подгрузить .env из корня репозитория (родитель каталога scripts/), если переменные ещё не заданы."""
    try:
        script_dir = Path(__file__).resolve().parent
        root = script_dir.parent
        env_file = root / ".env"
        if not env_file.is_file():
            return
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"").strip()
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        pass


_load_env_from_project_root()

PORT_HTTP = 8091
CDP_PORT = int(os.getenv("MEDIA_KIOSK_CDP_PORT", "9222"))
CHROMIUM_BIN = os.getenv("MEDIA_KIOSK_CHROMIUM", "").strip() or None
NO_LAUNCH = os.getenv("MEDIA_KIOSK_NO_LAUNCH", "").strip() in ("1", "true", "yes")
# Отдельный профиль, чтобы браузер не переиспользовал уже запущенный процесс (тот не слушает 9222)
USER_DATA_DIR = os.getenv("MEDIA_KIOSK_USER_DATA_DIR", "").strip() or os.path.join(os.path.expanduser("~"), ".cache", "media-kiosk-browser")
# Kodi JSON-RPC (порт 8080 по умолчанию; в Kodi: Настройки → Службы → Удалённый доступ по HTTP)
KODI_URL = (os.getenv("KODI_URL", "").strip() or "http://127.0.0.1:8080").rstrip("/")
KODI_LAUNCH_CMD = os.getenv("KODI_LAUNCH_CMD", "").strip() or None  # например "kodi" или "kodi-standalone"

try:
    import websocket
except ImportError:
    websocket = None  # type: ignore


def _find_chromium() -> str | None:
    if CHROMIUM_BIN:
        return CHROMIUM_BIN
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "yandex-browser"):
        try:
            subprocess.run([name, "--version"], capture_output=True, check=True, timeout=2)
            return name
        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
            continue
    return None


def _launch_chromium_kiosk() -> subprocess.Popen | None:
    if NO_LAUNCH:
        return None
    binary = _find_chromium()
    if not binary:
        print("Warning: Chromium not found. Start it manually with --remote-debugging-port=%s --kiosk" % CDP_PORT, file=sys.stderr)
        return None
    os.makedirs(USER_DATA_DIR, exist_ok=True)
    cmd = [
        binary,
        "--kiosk",
        "--remote-debugging-port=%s" % CDP_PORT,
        "--remote-allow-origins=*",
        "--user-data-dir=%s" % USER_DATA_DIR,
        "--no-first-run",
        "--disable-infobars",
        "--noerrdialogs",
        "about:blank",
    ]
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        # ждём, пока в CDP появится хотя бы одна страница (type=page)
        for i in range(60):
            try:
                with urlopen("http://127.0.0.1:%s/json" % CDP_PORT, timeout=1) as r:
                    data = json.loads(r.read().decode())
                if isinstance(data, list):
                    for item in data:
                        if item.get("type") == "page":
                            return p
            except Exception:
                pass
            time.sleep(0.5)
        print("Warning: Chromium CDP did not report a page in time.", file=sys.stderr)
        return p
    except Exception as e:
        print("Warning: could not start Chromium:", e, file=sys.stderr)
        return None


def _debug_cdp_dump() -> None:
    """Вывести в stderr, что вернул CDP — чтобы понять формат ответа браузера."""
    for path in ("/json", "/json/version"):
        try:
            with urlopen("http://127.0.0.1:%s%s" % (CDP_PORT, path), timeout=1) as r:
                raw = r.read().decode()
            data = json.loads(raw)
            if isinstance(data, list):
                types = [item.get("type", "?") for item in data]
                print("[media-executor-kiosk] CDP %s: %d targets, types=%s" % (path, len(data), types), file=sys.stderr)
            else:
                print("[media-executor-kiosk] CDP %s: %s" % (path, list(data.keys())[:8]), file=sys.stderr)
        except Exception as e:
            print("[media-executor-kiosk] CDP %s: %s" % (path, e), file=sys.stderr)


def _get_ws_url() -> str | None:
    """WebSocket URL у target с type page или tab (у browser target нет Page.navigate)."""
    for path in ("/json", "/json/list"):
        try:
            with urlopen("http://127.0.0.1:%s%s" % (CDP_PORT, path), timeout=2) as r:
                data = json.loads(r.read().decode())
            if not isinstance(data, list):
                continue
            for item in data:
                t = item.get("type")
                ws = item.get("webSocketDebuggerUrl")
                if ws and t in ("page", "tab"):
                    return ws
            # Часть сборок отдают только browser; у него нет Page, но можно попробовать
            for item in data:
                if item.get("webSocketDebuggerUrl") and item.get("type") != "browser":
                    return item["webSocketDebuggerUrl"]
        except Exception:
            continue
    return None


def _kodi_jsonrpc(method: str, params: dict | None = None) -> bool:
    try:
        payload = {"jsonrpc": "2.0", "method": method, "id": 1}
        if params:
            payload["params"] = params
        req = Request(
            KODI_URL + "/jsonrpc",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=3) as r:
            json.loads(r.read().decode())
        return True
    except (URLError, HTTPError, ValueError) as e:
        print("[media-executor-kiosk] Kodi %s: %s" % (method, e), file=sys.stderr)
        return False


def _kodi_get_active_player() -> int | None:
    try:
        payload = {"jsonrpc": "2.0", "method": "Player.GetActivePlayers", "id": 1}
        req = Request(
            KODI_URL + "/jsonrpc",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=3) as r:
            out = json.loads(r.read().decode())
        players = out.get("result") or []
        if players and isinstance(players, list) and players[0].get("playerid") is not None:
            return int(players[0]["playerid"])
    except Exception:
        pass
    return None


def _kodi_dispatch(action: str, url: str | None) -> bool:
    if action == "open_url" and (url == "kodi://" or not url or (isinstance(url, str) and url.strip() == "kodi://")):
        # Запуск Kodi по фразе «включи коди»
        to_try = [KODI_LAUNCH_CMD] if KODI_LAUNCH_CMD else []
        to_try += ["kodi", "kodi-standalone", "kodi.bin"]
        # типичные пути, если в PATH нет
        for path in ("/usr/bin/kodi", "/usr/local/bin/kodi"):
            if path not in to_try and os.path.isfile(path):
                to_try.append(path)
        for name in to_try:
            if not name:
                continue
            exe = name.split()[0] if name else None
            if not exe:
                continue
            print("[media-executor-kiosk] Kodi: attempting launch %s" % name, file=sys.stderr)
            try:
                subprocess.Popen(
                    name.split() if " " in name else [name],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                print("[media-executor-kiosk] Kodi: launched %s" % name, file=sys.stderr)
                return True
            except FileNotFoundError:
                print("[media-executor-kiosk] Kodi: not found %s" % exe, file=sys.stderr)
                continue
            except Exception as e:
                print("[media-executor-kiosk] Kodi: launch failed %s" % e, file=sys.stderr)
                continue
        print("[media-executor-kiosk] Kodi: no executable found, set KODI_LAUNCH_CMD in .env", file=sys.stderr)
        return False
    playerid = _kodi_get_active_player()
    if playerid is None:
        playerid = 0
    if action == "play":
        return _kodi_jsonrpc("Player.PlayPause", {"playerid": playerid})
    if action == "pause":
        return _kodi_jsonrpc("Player.PlayPause", {"playerid": playerid})
    if action == "next":
        return _kodi_jsonrpc("Player.GoTo", {"playerid": playerid, "to": "next"})
    if action == "prev":
        return _kodi_jsonrpc("Player.GoTo", {"playerid": playerid, "to": "previous"})
    if action == "open_url" and url and not url.startswith("kodi://"):
        return _kodi_jsonrpc("Player.Open", {"item": {"file": url}})
    return False


def _mpris_dispatch(action: str) -> bool:
    """Управление воспроизведением через MPRIS (playerctl): браузер (Spotify/VK), VLC и др."""
    mapping = {
        "play": ["playerctl", "play"],
        "pause": ["playerctl", "pause"],
        "next": ["playerctl", "next"],
        "prev": ["playerctl", "previous"],
        "volume_up": ["playerctl", "volume", "5%+"],
        "volume_down": ["playerctl", "volume", "5%-"],
    }
    args = mapping.get(action)
    if not args:
        return False
    try:
        r = subprocess.run(args, capture_output=True, timeout=3)
        if r.returncode != 0 and r.stderr:
            print("[media-executor-kiosk] MPRIS %s: %s" % (action, r.stderr.decode().strip() or "no player?"), file=sys.stderr)
        return r.returncode == 0
    except FileNotFoundError:
        print("[media-executor-kiosk] MPRIS: playerctl not installed (apt install playerctl)", file=sys.stderr)
        return False
    except Exception as e:
        print("[media-executor-kiosk] MPRIS %s: %s" % (action, e), file=sys.stderr)
        return False


# Deep-link главного экрана Stremio (Board). Голый stremio:// даёт initShellComm/чёрный экран.
STREMIO_BOARD_URL = "stremio:///board"


def _open_stremio(url: str) -> bool:
    """Запустить Stremio: нативный stremio, затем Flatpak; xdg-open часто даёт gio «not supported»."""
    url = (url or "").strip()
    if url in ("stremio://", "stremio:///", ""):
        url = STREMIO_BOARD_URL
    opts = {"check": True, "timeout": 10, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}

    # 1) Нативный stremio (PATH или /opt/stremio/stremio)
    for cmd in (["stremio", url], ["/opt/stremio/stremio", url]):
        try:
            subprocess.run(cmd, **opts)
            print("[media-executor-kiosk] Stremio: %s" % cmd[0], file=sys.stderr)
            return True
        except FileNotFoundError:
            continue
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            break  # найден, но упал — не пробуем flatpak с тем же URL

    # 2) Flatpak
    try:
        subprocess.run(["flatpak", "run", "com.stremio.Stremio", url], **opts)
        print("[media-executor-kiosk] Stremio: flatpak", file=sys.stderr)
        return True
    except FileNotFoundError:
        pass
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        print("[media-executor-kiosk] Stremio: flatpak failed", file=sys.stderr)
        return False

    # 3) xdg-open (gio часто не поддерживает stremio://)
    try:
        subprocess.run(["xdg-open", url], **opts)
        print("[media-executor-kiosk] Stremio: xdg-open", file=sys.stderr)
        return True
    except Exception as e:
        print("[media-executor-kiosk] Stremio: %s" % e, file=sys.stderr)
        return False


def _open_desktop_app(url: str) -> bool:
    """Открыть URL через xdg-open (для десктоп-приложений, не Stremio)."""
    try:
        subprocess.run(["xdg-open", url], check=True, timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("[media-executor-kiosk] xdg-open: opened %s" % url, file=sys.stderr)
        return True
    except subprocess.TimeoutExpired:
        print("[media-executor-kiosk] xdg-open: timeout for %s" % url, file=sys.stderr)
        return False
    except subprocess.CalledProcessError as e:
        print("[media-executor-kiosk] xdg-open: failed %s (exit %d)" % (url, e.returncode), file=sys.stderr)
        return False
    except FileNotFoundError:
        print("[media-executor-kiosk] xdg-open: not found (install xdg-utils)", file=sys.stderr)
        return False
    except Exception as e:
        print("[media-executor-kiosk] xdg-open: error %s" % e, file=sys.stderr)
        return False


def _navigate_via_cdp(url: str) -> bool:
    if not websocket:
        return False
    ws_url = _get_ws_url()
    if not ws_url:
        print("[media-executor-kiosk] CDP: no page target on port %s" % CDP_PORT, file=sys.stderr)
        _debug_cdp_dump()
        return False
    try:
        ws = websocket.create_connection(ws_url, timeout=5)
        ws.send(json.dumps({"id": 1, "method": "Page.navigate", "params": {"url": url}}))
        _ = ws.recv()
        ws.close()
        print("[media-executor-kiosk] CDP: navigated to %s" % url, file=sys.stderr)
        return True
    except Exception as e:
        print("[media-executor-kiosk] CDP navigate failed: %s" % e, file=sys.stderr)
        return False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print("[media-executor-kiosk]", format % args)

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
        target = (cmd.get("target") or "browser").lower()
        url = cmd.get("url") or ""
        print("[media-executor-kiosk] command: action=%s target=%s url=%s" % (action, target, url or "(empty)"), file=sys.stderr)
        result = {"ok": True, "action": action, "target": target}
        if target == "kodi":
            ok = _kodi_dispatch(action, url)
            if not ok:
                result["ok"] = False
                result["error"] = "Kodi failed (KODI_URL=%s, включён ли удалённый доступ в Kodi?)" % KODI_URL
            else:
                result["kodi"] = True
        elif target == "stremio" and action == "open_url":
            # Stremio: голый stremio:// заменяем на stremio:///board; запускаем нативный stremio или Flatpak.
            # Если видишь initShellComm + EADDRINUSE — освободи порты 11470/12470 (см. docs/torrents.md).
            ok = _open_stremio(url or "stremio://")
            if ok:
                result["opened"] = url or "stremio"
            else:
                result["ok"] = False
                result["error"] = "Stremio не запустился (установлен ли stremio или Flatpak com.stremio.Stremio?)"
        elif target == "browser" and action in ("pause", "play", "next", "prev", "volume_up", "volume_down"):
            ok = _mpris_dispatch(action)
            if not ok:
                result["ok"] = False
                result["error"] = "MPRIS/playerctl failed (установи playerctl; должен быть активный плеер, например вкладка Spotify/VK)"
            else:
                result["mpris"] = True
        elif action == "open_url" and url:
            ok = _navigate_via_cdp(url)
            if not ok:
                time.sleep(1)
                ok = _navigate_via_cdp(url)
            if ok:
                result["opened"] = url
            else:
                result["ok"] = False
                result["error"] = "CDP navigate failed (Chromium with --remote-debugging-port=%s?)" % CDP_PORT
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())


def main():
    if not websocket:
        print("Install: pip install websocket-client", file=sys.stderr)
        sys.exit(1)
    if not NO_LAUNCH:
        _launch_chromium_kiosk()
    print("Media executor (kiosk) listening on 0.0.0.0:%s" % PORT_HTTP)
    print("CDP port: %s. Kodi: %s" % (CDP_PORT, KODI_URL))
    print("Set MEDIA_EXECUTOR_URL=http://host.docker.internal:%s" % PORT_HTTP)
    print("If CDP reports 'no page target': start browser manually with --remote-debugging-port=%s --kiosk, then run this script with MEDIA_KIOSK_NO_LAUNCH=1" % CDP_PORT, file=sys.stderr)
    HTTPServer(("0.0.0.0", PORT_HTTP), Handler).serve_forever()


if __name__ == "__main__":
    main()
    sys.exit(0)

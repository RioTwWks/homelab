/* ═══════════════════════════════════════════════════
   Moltbot UI v3
   Chat · Markdown · Typing · Voice · TTS
   Sessions · Toasts · Status
   ═══════════════════════════════════════════════════ */

// ─── DOM ───
const $chat       = document.getElementById("chat");
const $composer   = document.getElementById("composer");
const $text       = document.getElementById("text");
const $mode       = document.getElementById("mode");
const $status     = document.getElementById("status");
const $clearChat  = document.getElementById("clearChat");
const $clearAll   = document.getElementById("clearAll");
const $showMeta   = document.getElementById("showMeta");
const $showSrc    = document.getElementById("showSources");
const $connDot    = document.getElementById("connDot");
const $statusGrid = document.getElementById("statusGrid");
const $modelsInfo = document.getElementById("modelsInfo");
const $micBtn     = document.getElementById("micBtn");
const $sessList   = document.getElementById("sessionList");
const $newSess    = document.getElementById("newSession");
const $toasts     = document.getElementById("toasts");
const $sidebar   = document.getElementById("sidebar");
const $sidebarToggle  = document.getElementById("sidebarToggle");
const $sidebarBackdrop = document.getElementById("sidebarBackdrop");
const $topbarTabs     = document.getElementById("topbarTabs");
const $dashboardGrid   = document.getElementById("dashboardGrid");
const $dashboardFooter = document.getElementById("dashboardFooter");
const $homelabModeStatus = document.getElementById("homelabModeStatus");
const $homelabModeBtns = document.querySelectorAll("[data-homelab-mode]");
const HOMELAB_MODE_LABELS = { ai: "AI", gaming: "Gaming", media: "Media" };
let homelabModeBusy = false;
function setHomelabModeUi(mode, message) {
  const m = (mode || "").toLowerCase();
  $homelabModeBtns.forEach(btn => { btn.classList.toggle("active", btn.dataset.homelabMode === m); btn.disabled = homelabModeBusy; });
  if ($homelabModeStatus) $homelabModeStatus.textContent = message || `Текущий режим: ${HOMELAB_MODE_LABELS[m] || m || "—"}`;
}
async function loadHomelabMode() {
  if (!$homelabModeStatus) return;
  try {
    const r = await fetch("/api/v1/system/homelab-mode", { signal: AbortSignal.timeout(8000) });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const st = (await r.json()).state || {};
    setHomelabModeUi(st.mode, st.message ? `${HOMELAB_MODE_LABELS[st.mode] || st.mode}: ${st.message}` : undefined);
  } catch (e) { setHomelabModeUi("", `Режим недоступен (${e?.message})`); }
}
async function switchHomelabMode(mode) {
  if (homelabModeBusy || !mode) return;
  homelabModeBusy = true; setHomelabModeUi(mode, "Переключение…");
  try {
    const r = await fetch("/api/v1/system/homelab-mode", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ mode }), signal: AbortSignal.timeout(120000) });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data?.detail || `HTTP ${r.status}`);
    let hint = data.state?.message || "ok";
    if (data.executor?.skipped) hint += " (HOMELAB_MODE_EXECUTOR_URL)";
    setHomelabModeUi(mode, `${HOMELAB_MODE_LABELS[mode]}: ${hint}`);
    toast(`Режим ${HOMELAB_MODE_LABELS[mode]}`, "info");
  } catch (e) { setHomelabModeUi(mode, `Ошибка: ${e?.message}`); toast("Не удалось переключить режим", "error"); }
  finally { homelabModeBusy = false; $homelabModeBtns.forEach(b => { b.disabled = false; }); loadHomelabMode(); }
}
$homelabModeBtns.forEach(btn => btn.addEventListener("click", () => { switchHomelabMode(btn.dataset.homelabMode); if (window.innerWidth <= 768) closeSidebar(); }));

/* ─── Service registry for Dashboard (url = open in browser, probeUrl = backend GET from Docker network) ─── */
const SERVICES = [
  { id: "moltbot-api",  name: "Moltbot API",   icon: "🤖", cat: "core",   url: "http://localhost:18080",  probeUrl: "http://moltbot-api:8080/healthz" },
  { id: "ollama",       name: "Ollama",        icon: "🧠", cat: "core",   url: "http://localhost:11434",  probeUrl: "" },
  { id: "redis",        name: "Redis",        icon: "🗄",  cat: "core",   url: null,                     probeUrl: "" },
  { id: "qdrant",       name: "Qdrant",        icon: "📊", cat: "core",   url: "http://localhost:6333/dashboard", probeUrl: "http://qdrant:6333/" },
  { id: "media-api",    name: "Media API",     icon: "▶",  cat: "core",   url: "http://localhost:8090",  probeUrl: "http://media-api:8090/healthz" },
  { id: "homeassistant", name: "Home Assistant", icon: "🏠", cat: "ha",   url: "http://localhost:8123",  probeUrl: "http://homeassistant:8123/api/" },
  { id: "nextcloud",    name: "Nextcloud",     icon: "☁️", cat: "storage", url: "http://localhost:18082", probeUrl: "http://nextcloud:80/" },
  { id: "immich",      name: "Immich",        icon: "📷", cat: "photos",  url: "http://localhost:18083", probeUrl: "http://immich-server:2283/" },
  { id: "qbittorrent", name: "qBittorrent",   icon: "📥", cat: "torrents", url: "http://localhost:18084", probeUrl: "http://qbittorrent:8080/" },
  { id: "stremio",     name: "Stremio Server", icon: "🎬", cat: "torrents", url: "http://localhost:11480", probeUrl: "http://stremio-server:11470/" },
  { id: "torrserver",  name: "TorrServer",    icon: "🌊", cat: "torrents", url: "http://localhost:18086", probeUrl: "http://torrserver:5665/" },
  { id: "jacred",      name: "Jacred",        icon: "📂", cat: "torrents", url: "http://localhost:18087", probeUrl: "http://jacred:9117/" },
  { id: "searxng",     name: "SearXNG",       icon: "🔎", cat: "search",  url: "http://localhost:18081", probeUrl: "http://searxng:8080/" },
];

const CATEGORIES = [
  { id: "core",    label: "Ядро" },
  { id: "ha",      label: "Умный дом" },
  { id: "storage", label: "Хранилище" },
  { id: "photos",  label: "Фото" },
  { id: "torrents", label: "Медиа / Торренты" },
  { id: "search",  label: "Поиск" },
];

/* ═══════════════════════
   1. TOASTS
   ═══════════════════════ */
function toast(msg, type = "info") {
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = msg;
  $toasts.appendChild(el);
  setTimeout(() => el.remove(), 3200);
}

/* ═══════════════════════
   2. HELPERS
   ═══════════════════════ */
function esc(s) {
  const d = document.createElement("div");
  d.textContent = String(s ?? "");
  return d.innerHTML;
}

function fmtTime(ts) {
  return (ts ? new Date(ts) : new Date()).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
}

/* ═══════════════════════
   4. MARKDOWN → HTML (lightweight)
   ═══════════════════════ */
function md(raw) {
  let s = esc(raw);
  // fenced code blocks
  s = s.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, _lang, code) =>
    `<pre><code>${code.trim()}</code></pre>`
  );
  // inline code
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  // bold
  s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  // italic (single *)
  s = s.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, "<em>$1</em>");
  // unordered list
  s = s.replace(/^[\-\*] (.+)$/gm, "<li>$1</li>");
  s = s.replace(/((?:<li>.*<\/li>\s*)+)/g, "<ul>$1</ul>");
  // ordered list
  s = s.replace(/^\d+\.\s+(.+)$/gm, "<li>$1</li>");
  // double newline → paragraph break
  s = s.replace(/\n{2,}/g, "</p><p>");
  // single newline → <br>
  s = s.replace(/\n/g, "<br>");
  return `<p>${s}</p>`;
}

/* ═══════════════════════
   5. SESSION MANAGER (localStorage)
   ═══════════════════════ */
const STORE_SESSIONS = "moltbot_sessions";   // { id, name, messages[] }[]
const STORE_ACTIVE   = "moltbot_active_sess";
const MAX_MSG = 200;

function uid() { return Date.now().toString(36) + Math.random().toString(36).slice(2, 6); }

function getSessions() {
  try { return JSON.parse(localStorage.getItem(STORE_SESSIONS) || "[]"); }
  catch { return []; }
}
function saveSessions(list) { localStorage.setItem(STORE_SESSIONS, JSON.stringify(list)); }

function getActiveId() { return localStorage.getItem(STORE_ACTIVE) || ""; }
function setActiveId(id) { localStorage.setItem(STORE_ACTIVE, id); }

function getActive() {
  let list = getSessions();
  let id = getActiveId();
  let s = list.find(x => x.id === id);
  if (!s) {
    s = { id: uid(), name: "webui", messages: [] };
    list.push(s);
    saveSessions(list);
    setActiveId(s.id);
  }
  return s;
}

function pushMsg(role, text, meta) {
  const list = getSessions();
  const s = list.find(x => x.id === getActiveId());
  if (!s) return;
  s.messages.push({ role, text, meta: meta || null, ts: Date.now() });
  if (s.messages.length > MAX_MSG) s.messages.splice(0, s.messages.length - MAX_MSG);
  saveSessions(list);
}

function renderSessionList() {
  const list = getSessions();
  const active = getActiveId();
  $sessList.innerHTML = "";
  list.forEach(s => {
    const el = document.createElement("div");
    el.className = `session-item${s.id === active ? " active" : ""}`;
    el.innerHTML = `<span class="s-name">${esc(s.name)}</span><span class="s-del" title="Удалить">✕</span>`;
    el.querySelector(".s-name").addEventListener("click", () => {
      switchSession(s.id);
      if (window.innerWidth <= 768) closeSidebar();
    });
    el.querySelector(".s-del").addEventListener("click", e => { e.stopPropagation(); deleteSession(s.id); });
    $sessList.appendChild(el);
  });
}

function switchSession(id) {
  setActiveId(id);
  renderSessionList();
  restoreChat();
}

function deleteSession(id) {
  let list = getSessions().filter(x => x.id !== id);
  saveSessions(list);
  if (getActiveId() === id) {
    if (list.length) setActiveId(list[0].id);
    else { setActiveId(""); getActive(); }
  }
  renderSessionList();
  restoreChat();
  toast("Сессия удалена", "info");
}

$newSess.addEventListener("click", () => {
  const name = prompt("Имя сессии:", `сессия-${getSessions().length + 1}`);
  if (!name) return;
  const s = { id: uid(), name, messages: [] };
  const list = getSessions();
  list.push(s);
  saveSessions(list);
  setActiveId(s.id);
  renderSessionList();
  restoreChat();
  toast(`Сессия «${name}» создана`, "success");
});

/* ═══════════════════════
   6. MESSAGE RENDERING
   ═══════════════════════ */
function buildMsg(role, text, meta, ts) {
  const wrap = document.createElement("div");
  wrap.className = `msg ${role}`;

  const av = document.createElement("div");
  av.className = "msg-avatar";
  av.textContent = role === "user" ? "👤" : "🤖";
  wrap.appendChild(av);

  const body = document.createElement("div");
  body.className = "msg-body";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  if (role === "assistant") {
    bubble.innerHTML = md(text);
  } else {
    bubble.textContent = text;
  }

  // meta
  if (meta && ($showMeta.checked || $showSrc.checked)) {
    if ($showMeta.checked && (meta.intent || meta.used_model || meta.timings_ms)) {
      const m = document.createElement("div");
      m.className = "meta";
      const parts = [];
      if (meta.intent)     parts.push(`intent=${meta.intent}`);
      if (meta.used_model) parts.push(`model=${meta.used_model}`);
      if (meta.timings_ms) parts.push(`timings=${JSON.stringify(meta.timings_ms)}`);
      m.textContent = parts.join(" · ");
      bubble.appendChild(m);
    }
    if ($showSrc.checked && Array.isArray(meta.sources) && meta.sources.length) {
      const s = document.createElement("div");
      s.className = "sources";
      s.textContent = "sources: " + meta.sources.map(x => JSON.stringify(x)).join(" ");
      bubble.appendChild(s);
    }
  }

  body.appendChild(bubble);

  // footer: time + actions
  const footer = document.createElement("div");
  footer.className = "msg-footer";

  const time = document.createElement("span");
  time.className = "msg-time";
  time.textContent = fmtTime(ts);
  footer.appendChild(time);

  if (role === "assistant") {
    const actions = document.createElement("span");
    actions.className = "msg-actions";

    // copy
    const copyBtn = document.createElement("button");
    copyBtn.className = "action-btn";
    copyBtn.textContent = "копировать";
    copyBtn.addEventListener("click", () => {
      navigator.clipboard.writeText(text).then(() => {
        toast("Скопировано", "success");
        copyBtn.textContent = "✓";
        setTimeout(() => (copyBtn.textContent = "копировать"), 1200);
      });
    });
    actions.appendChild(copyBtn);

    // TTS
    const ttsBtn = document.createElement("button");
    ttsBtn.className = "action-btn";
    ttsBtn.textContent = "🔊";
    ttsBtn.title = "Озвучить";
    ttsBtn.addEventListener("click", () => speakText(text, ttsBtn));
    actions.appendChild(ttsBtn);

    footer.appendChild(actions);
  }

  body.appendChild(footer);
  wrap.appendChild(body);
  return wrap;
}

function appendMsg(role, text, meta) {
  hideWelcome();
  $chat.appendChild(buildMsg(role, text, meta));
  $chat.scrollTop = $chat.scrollHeight;
}

/* ═══════════════════════
   7. WELCOME SCREEN
   ═══════════════════════ */
const WELCOME_SUGGESTIONS = [
  { text: "Какая погода?", label: "🌤 погода" },
  { text: "Последние новости", label: "📰 новости" },
  { text: "поставь таймер на 3 минуты", label: "⏱ таймер" },
  { text: "ютуб", label: "▶ ютуб" },
  { text: "включи свет в гостиной", label: "💡 свет" },
  { text: "режим кино", label: "🎬 кино" },
];

function showWelcome() {
  if ($chat.querySelector(".welcome")) return;
  const w = document.createElement("div");
  w.className = "welcome";
  w.innerHTML = `
    <div class="welcome-logo">🤖</div>
    <h2>Привет! Я Moltbot.</h2>
    <p>Голосовой ассистент для твоего homelab. Задай вопрос, дай команду или попробуй что-нибудь из подсказок:</p>
    <div class="welcome-chips"></div>
  `;
  const chips = w.querySelector(".welcome-chips");
  WELCOME_SUGGESTIONS.forEach(s => {
    const c = document.createElement("button");
    c.className = "welcome-chip";
    c.textContent = s.label;
    c.addEventListener("click", () => send(s.text));
    chips.appendChild(c);
  });
  $chat.appendChild(w);
}

function hideWelcome() {
  const w = $chat.querySelector(".welcome");
  if (w) w.remove();
}

/* ═══════════════════════
   8. TYPING INDICATOR
   ═══════════════════════ */
let typingEl = null;
function showTyping() {
  if (typingEl) return;
  typingEl = document.createElement("div");
  typingEl.className = "msg assistant";
  typingEl.innerHTML = `
    <div class="msg-avatar">🤖</div>
    <div class="msg-body">
      <div class="bubble typing-dots">
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
      </div>
    </div>`;
  $chat.appendChild(typingEl);
  $chat.scrollTop = $chat.scrollHeight;
}
function hideTyping() {
  if (typingEl) { typingEl.remove(); typingEl = null; }
}

/* ═══════════════════════
   9. RESTORE CHAT
   ═══════════════════════ */
function restoreChat() {
  $chat.innerHTML = "";
  const s = getActive();
  if (!s.messages.length) {
    showWelcome();
    return;
  }
  s.messages.forEach(m => {
    $chat.appendChild(buildMsg(m.role, m.text, m.meta, m.ts));
  });
  $chat.scrollTop = $chat.scrollHeight;
}

/* ═══════════════════════
   10. SEND
   ═══════════════════════ */
async function send(text) {
  const t = String(text || "").trim();
  if (!t) return;

  appendMsg("user", t);
  pushMsg("user", t);
  $status.textContent = "";
  showTyping();

  const sess = getActive();
  const payload = {
    text: t,
    session_id: sess.name || "webui",
    mode: $mode.value || "auto",
  };

  try {
    let r = await fetch("/api/v1/chat/stream", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    hideTyping();

    if (!r.ok) {
      if (r.status === 404) {
        r = await fetch("/api/v1/chat", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!r.ok) {
          const body = await r.text();
          throw new Error(`HTTP ${r.status}: ${body.slice(0, 300)}`);
        }
        const data = await r.json();
        const reply = data.reply_text || "(пустой ответ)";
        appendMsg("assistant", reply, data);
        pushMsg("assistant", reply, data);
        return;
      }
      const body = await r.text();
      throw new Error(`HTTP ${r.status}: ${body.slice(0, 300)}`);
    }

    hideWelcome();
    const msgWrap = buildMsg("assistant", "", null);
    const bubble = msgWrap.querySelector(".bubble");
    $chat.appendChild(msgWrap);
    $chat.scrollTop = $chat.scrollHeight;

    let accumulated = "";
    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buffer.indexOf("\n\n")) >= 0) {
        const part = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        const dataStart = part.indexOf("data: ");
        if (dataStart >= 0) {
          const jsonStr = part.slice(dataStart + 6).trim();
          if (!jsonStr) continue;
          try {
            const event = JSON.parse(jsonStr);
            if (event.chunk !== undefined) {
              accumulated += event.chunk || "";
              bubble.innerHTML = md(accumulated);
              $chat.scrollTop = $chat.scrollHeight;
            } else if (event.done === true) {
              const reply = event.reply_text || accumulated || "(пустой ответ)";
              msgWrap.remove();
              appendMsg("assistant", reply, event);
              pushMsg("assistant", reply, event);
              return;
            }
          } catch (_) {}
        }
      }
    }
    const reply = accumulated || "(пустой ответ)";
    msgWrap.remove();
    appendMsg("assistant", reply, {});
    pushMsg("assistant", reply, {});
  } catch (e) {
    hideTyping();
    const err = `Ошибка: ${e?.message || e}`;
    appendMsg("assistant", err, { intent: "error" });
    pushMsg("assistant", err, { intent: "error" });
    toast(err, "error");
  }
}

/* ═══════════════════════
   11. VOICE INPUT (Web Speech API)
   ═══════════════════════ */
let recognition = null;
let isRecording = false;

function initSpeechRecognition() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    $micBtn.title = "SpeechRecognition не поддерживается в этом браузере";
    $micBtn.style.opacity = "0.3";
    $micBtn.style.cursor = "not-allowed";
    return;
  }
  recognition = new SR();
  recognition.lang = "ru-RU";
  recognition.interimResults = false;
  recognition.continuous = false;

  recognition.addEventListener("result", ev => {
    const text = ev.results[0][0].transcript;
    $text.value = text;
    toast(`🎤 "${text}"`, "info");
    // auto-send after recognition
    send(text);
    $text.value = "";
  });
  recognition.addEventListener("end", () => {
    isRecording = false;
    $micBtn.classList.remove("recording");
  });
  recognition.addEventListener("error", ev => {
    isRecording = false;
    $micBtn.classList.remove("recording");
    if (ev.error !== "aborted") {
      toast(`Ошибка распознавания: ${ev.error}`, "error");
    }
  });
}

$micBtn.addEventListener("click", () => {
  if (!recognition) { toast("Голос не поддерживается", "error"); return; }
  if (isRecording) {
    recognition.abort();
    isRecording = false;
    $micBtn.classList.remove("recording");
  } else {
    recognition.start();
    isRecording = true;
    $micBtn.classList.add("recording");
    toast("Слушаю…", "info");
  }
});

/* ═══════════════════════
   12. TTS (SpeechSynthesis)
   ═══════════════════════ */
let currentUtterance = null;

function speakText(text, btn) {
  // if already speaking this text, stop
  if (speechSynthesis.speaking && currentUtterance) {
    speechSynthesis.cancel();
    currentUtterance = null;
    if (btn) btn.textContent = "🔊";
    return;
  }

  // strip markdown artifacts for cleaner speech
  const clean = text
    .replace(/```[\s\S]*?```/g, " код пропущен ")
    .replace(/`[^`]+`/g, "")
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/\*(.+?)\*/g, "$1")
    .replace(/#+\s/g, "")
    .replace(/\[.*?\]\(.*?\)/g, "");

  const utter = new SpeechSynthesisUtterance(clean);
  utter.lang = "ru-RU";
  utter.rate = 1.05;
  currentUtterance = utter;

  if (btn) btn.textContent = "⏹";
  utter.addEventListener("end", () => {
    currentUtterance = null;
    if (btn) btn.textContent = "🔊";
  });
  utter.addEventListener("error", () => {
    currentUtterance = null;
    if (btn) btn.textContent = "🔊";
  });

  speechSynthesis.speak(utter);
}

/* ═══════════════════════
   13. EVENTS
   ═══════════════════════ */
$composer.addEventListener("submit", ev => {
  ev.preventDefault();
  const t = $text.value;
  $text.value = "";
  send(t);
});

$text.addEventListener("keydown", ev => {
  if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) {
    ev.preventDefault();
    $composer.requestSubmit();
  }
});

document.querySelectorAll(".chip").forEach(btn => {
  btn.addEventListener("click", () => {
    send(btn.dataset.text || "");
    if (window.innerWidth <= 768) closeSidebar();
  });
});

$clearChat.addEventListener("click", () => {
  $chat.innerHTML = "";
  showWelcome();
  $text.focus();
});

$clearAll.addEventListener("click", () => {
  if (!confirm("Удалить историю текущей сессии?")) return;
  const list = getSessions();
  const s = list.find(x => x.id === getActiveId());
  if (s) { s.messages = []; saveSessions(list); }
  $chat.innerHTML = "";
  showWelcome();
  toast("История очищена", "info");
});

/* ═══════════════════════
   14. CONNECTION PROBE
   ═══════════════════════ */
async function probeConn() {
  try {
    const r = await fetch("/api/healthz", { signal: AbortSignal.timeout(3000) });
    $connDot.className = `conn-dot ${r.ok ? "online" : "offline"}`;
  } catch {
    $connDot.className = "conn-dot offline";
  }
}
probeConn();
setInterval(probeConn, 15000);

/* ═══════════════════════
   15. STATUS PAGE
   ═══════════════════════ */
async function loadStatus() {
  $statusGrid.innerHTML = '<div class="status-placeholder">Загрузка…</div>';
  $modelsInfo.innerHTML = "—";
  try {
    const r = await fetch("/api/v1/system/status");
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    const svc = data.services || {};
    if (!Object.keys(svc).length) {
      $statusGrid.innerHTML = '<div class="status-placeholder">Нет данных</div>';
    } else {
      $statusGrid.innerHTML = "";
      for (const [name, st] of Object.entries(svc)) {
        const ok = st === "ok";
        const card = document.createElement("div");
        card.className = "svc-card";
        card.innerHTML = `
          <div class="svc-name">${esc(name)}</div>
          <div class="svc-status"><span class="dot ${ok ? "ok" : "err"}"></span>${esc(st)}</div>`;
        $statusGrid.appendChild(card);
      }
    }
    const m = data.models || {};
    if (m.fast || m.chat) {
      $modelsInfo.className = "models-info";
      $modelsInfo.innerHTML = `
        <div><span class="label">fast</span>${esc(m.fast) || "—"}</div>
        <div><span class="label">chat</span>${esc(m.chat) || "—"}</div>`;
    }
  } catch (e) {
    $statusGrid.innerHTML = `<div class="status-placeholder" style="color:var(--danger)">${esc(e?.message)}</div>`;
  }
}

/* ═══════════════════════
   DASHBOARD PAGE
   ═══════════════════════ */
function portFromUrl(u) {
  if (!u) return "";
  try {
    const p = new URL(u).port;
    return p ? ":" + p : "";
  } catch { return ""; }
}

async function loadDashboard() {
  if (!$dashboardGrid) return;

  $dashboardGrid.innerHTML = "";
  $dashboardFooter.textContent = "Загрузка…";

  const byCat = {};
  CATEGORIES.forEach(c => { byCat[c.id] = []; });
  SERVICES.forEach(s => {
    if (byCat[s.cat]) byCat[s.cat].push(s);
  });

  const probePayload = SERVICES.filter(s => s.probeUrl != null).map(s => ({ name: s.id, url: s.probeUrl || "" }));
  let results = {};
  try {
    const r = await fetch("/api/v1/system/services", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(probePayload),
    });
    if (r.ok) {
      const data = await r.json();
      results = data.services || {};
    }
  } catch (_) {}
  // redis и ollama перезаписываем из GET /system/status (API уже их там проверяет)
  try {
    const statusRes = await fetch("/api/v1/system/status");
    if (statusRes.ok) {
      const d = await statusRes.json();
      const svc = d.services || {};
      if (svc.redis) results.redis = svc.redis;
      if (svc.ollama) results.ollama = svc.ollama;
    }
  } catch (_) {}

  CATEGORIES.forEach(cat => {
    const items = byCat[cat.id];
    if (!items.length) return;

    const section = document.createElement("div");
    section.className = "dash-category";
    const header = document.createElement("button");
    header.type = "button";
    header.className = "dash-category-header";
    header.innerHTML = `<span class="dash-category-label">${esc(cat.label)}</span><span class="dash-category-toggle">▼</span>`;
    header.addEventListener("click", () => section.classList.toggle("collapsed"));

    const grid = document.createElement("div");
    grid.className = "dash-grid";

    items.forEach(s => {
      const st = results[s.id];
      const isOk = st === "ok";
      const isUnknown = st === undefined || st === "skip";
      const statusClass = isOk ? "ok" : isUnknown ? "unknown" : "err";
      const statusText = isOk ? "online" : isUnknown ? "—" : "offline";

      const card = document.createElement("div");
      card.className = `dash-card dash-card--${statusClass}`;
      const port = portFromUrl(s.url);
      card.innerHTML = `
        <div class="dash-card-icon">${esc(s.icon)}</div>
        <div class="dash-card-body">
          <div class="dash-card-name">${esc(s.name)}</div>
          <div class="dash-card-status"><span class="dot ${statusClass}"></span>${esc(statusText)}</div>
          ${s.url ? `<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer" class="dash-card-open">Открыть</a>` : ""}
          ${port ? `<span class="dash-card-port">${esc(port)}</span>` : ""}
        </div>`;
      grid.appendChild(card);
    });

    section.appendChild(header);
    section.appendChild(grid);
    $dashboardGrid.appendChild(section);
  });

  $dashboardFooter.textContent = "Обновлено " + new Date().toLocaleTimeString("ru-RU");
}

function refreshRightPanel() {
  loadDashboard();
  loadStatus();
loadHomelabMode();
}
document.getElementById("refreshRightPanel")?.addEventListener("click", refreshRightPanel);

/* ═══════════════════════
   THEME (light / dark)
   ═══════════════════════ */
const STORE_THEME = "moltbot_theme";
const THEME_DARK = "dark";
const THEME_LIGHT = "light";

function getTheme() {
  const stored = localStorage.getItem(STORE_THEME);
  if (stored === THEME_LIGHT || stored === THEME_DARK) return stored;
  if (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches) return THEME_LIGHT;
  return THEME_DARK;
}

function applyTheme(theme) {
  const isLight = theme === THEME_LIGHT;
  document.documentElement.setAttribute("data-theme", isLight ? THEME_LIGHT : "");
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = isLight ? "#e8ecf4" : "#050910";
}

function setTheme(theme) {
  localStorage.setItem(STORE_THEME, theme);
  applyTheme(theme);
}

applyTheme(getTheme());

document.getElementById("themeToggle")?.addEventListener("click", () => {
  const next = getTheme() === THEME_LIGHT ? THEME_DARK : THEME_LIGHT;
  setTheme(next);
});

/* ═══════════════════════
   MOBILE: sidebar drawer + Chat/Dashboard tabs
   ═══════════════════════ */
function openSidebar() {
  document.body.classList.add("sidebar-open");
  if ($sidebarBackdrop) $sidebarBackdrop.setAttribute("aria-hidden", "false");
}
function closeSidebar() {
  document.body.classList.remove("sidebar-open");
  if ($sidebarBackdrop) $sidebarBackdrop.setAttribute("aria-hidden", "true");
}
function setMobileView(view) {
  if (view === "dashboard") {
    document.body.classList.add("mobile-view-dashboard");
  } else {
    document.body.classList.remove("mobile-view-dashboard");
  }
  document.querySelectorAll(".topbar-tab").forEach(t => {
    t.classList.toggle("active", t.dataset.view === view);
  });
  closeSidebar();
}

if ($sidebarToggle) {
  $sidebarToggle.addEventListener("click", () => {
    document.body.classList.toggle("sidebar-open");
    if ($sidebarBackdrop) {
      $sidebarBackdrop.setAttribute("aria-hidden", document.body.classList.contains("sidebar-open") ? "false" : "true");
    }
  });
}
if ($sidebarBackdrop) {
  $sidebarBackdrop.addEventListener("click", closeSidebar);
}
if ($topbarTabs) {
  $topbarTabs.querySelectorAll(".topbar-tab").forEach(tab => {
    tab.addEventListener("click", () => setMobileView(tab.dataset.view || "chat"));
  });
  if (window.matchMedia("(max-width: 768px)").matches) $topbarTabs.setAttribute("aria-hidden", "false");
  window.matchMedia("(max-width: 768px)").addEventListener("change", ev => {
    $topbarTabs.setAttribute("aria-hidden", ev.matches ? "false" : "true");
  });
}

/* ═══════════════════════
   16. INIT
   ═══════════════════════ */
initSpeechRecognition();
getActive(); // ensure at least one session
renderSessionList();
restoreChat();
loadDashboard();
loadStatus();
loadHomelabMode();

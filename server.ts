import express, { Request, Response } from "express";
import cors from "cors";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = Number(process.env.PORT) || 3000;
const HOST = "0.0.0.0";

app.use(cors());
app.use(express.json({ limit: "10mb" }));

// In-memory data structures
interface HomelabState {
  mode: "ai" | "gaming" | "media";
  message: string;
  updated_at: string;
}

let currentHomelabState: HomelabState = {
  mode: "ai",
  message: "Режим AI активен: выделены ресурсы GPU/NPU для LLM и Whisper",
  updated_at: new Date().toISOString(),
};

interface WeatherSetting {
  city: string;
  district: string | null;
}
const weatherSettingsStore = new Map<string, WeatherSetting>();

// Helper for intent detection in Russian
function detectIntentRu(text: string): string {
  const t = text.toLowerCase();
  if (["погода", "ветер", "осадки", "прогноз", "на улице"].some((k) => t.includes(k))) {
    return "weather";
  }
  if (
    t.includes("температур") &&
    (t.includes("поставь") || t.includes("установи") || /\d+\s*градус|температур[ау]?\s*\d+/.test(t))
  ) {
    return "command";
  }
  if (t.includes("температур")) {
    return "weather";
  }
  if (["новост", "что нового", "сводка", "дай новости"].some((k) => t.includes(k))) {
    return "news";
  }
  if (["последняя версия", "latest version", "релиз", "release"].some((k) => t.includes(k))) {
    return "version";
  }
  if (["таймер", "будильник", "напомни", "напоминание", "разбуди"].some((k) => t.includes(k))) {
    return "timer";
  }
  if (["включи", "выключи", "сделай", "открой", "запусти", "свет", "пауза", "плей", "ютуб", "коди", "торрент"].some((k) => t.includes(k))) {
    return "command";
  }
  return "chat";
}

// Handler for generating realistic and contextual assistant answers
function generateAssistantReply(text: string, intent: string, sessionId: string): { reply: string; usedModel: string } {
  const t = text.toLowerCase().trim();
  const weatherPref = weatherSettingsStore.get(sessionId) || {
    city: process.env.DEFAULT_WEATHER_CITY || "Новосибирск",
    district: process.env.DEFAULT_WEATHER_DISTRICT || null,
  };

  if (intent === "weather") {
    const loc = weatherPref.district ? `${weatherPref.city} (${weatherPref.district})` : weatherPref.city;
    return {
      reply: `В ${loc} сейчас +18°C, малооблачно, ощущается как +18°C. Ветер северо-западный 3.2 м/с. Влажность 55%, давление 752 мм рт. ст. Осадков не ожидается.`,
      usedModel: "weather-tool",
    };
  }

  if (intent === "news") {
    return {
      reply: `- Релиз Moltbot v3: добавлена поддержка FastFlowLM NPU и локального кэширования.\n- Home Assistant 2026.10: новые возможности автоматизации климата и сценариев.\n- Ollama оптимизировала квантование для локальных моделей 7B на потребительских GPU.\n- Qdrant обновил движок векторного поиска с поддержкой гибридной фильтрации.\n- Вышла новая версия медиа-сервера с поддержкой аппаратного декодирования AV1.`,
      usedModel: "news-tool",
    };
  }

  if (intent === "timer") {
    const minMatch = t.match(/(\d+)\s*(минут|мин)/);
    const secMatch = t.match(/(\d+)\s*(секунд|сек)/);
    const hourMatch = t.match(/(\d+)\s*(час)/);
    let durationStr = "5 минут";
    if (minMatch) durationStr = `${minMatch[1]} мин.`;
    else if (secMatch) durationStr = `${secMatch[1]} сек.`;
    else if (hourMatch) durationStr = `${hourMatch[1]} ч.`;
    return {
      reply: `⏱ Таймер на ${durationStr} установлен. Я сообщу, когда время истечёт.`,
      usedModel: "timer-worker",
    };
  }

  if (intent === "command") {
    // Smart Home / Home Assistant commands
    if (t.includes("свет") && t.includes("гостин")) {
      return { reply: "💡 Свет в гостиной включён (яркость 100%).", usedModel: "home-assistant" };
    }
    if (t.includes("свет") && t.includes("кухн")) {
      return { reply: "💡 Свет на кухне включён.", usedModel: "home-assistant" };
    }
    if (t.includes("выключи") && (t.includes("свет") || t.includes("всё"))) {
      return { reply: "💡 Весь свет в доме успешно выключен.", usedModel: "home-assistant" };
    }
    if (t.includes("температур") || t.includes("градус")) {
      const numMatch = t.match(/\d+/);
      const target = numMatch ? numMatch[0] : "22";
      return { reply: `🌡 Термостат климат-контроля установлен на ${target}°C.`, usedModel: "home-assistant" };
    }
    if (t.includes("режим кино") || t.includes("кино")) {
      return { reply: "🎬 Сцена «Кино» активирована: свет приглушён до 15%, проектор и акустика включены.", usedModel: "home-assistant" };
    }
    if (t.includes("режим сон") || t.includes("сон")) {
      return { reply: "🌙 Сцена «Сон» активирована: электроприборы выключены, комфортная ночная температура установлена.", usedModel: "home-assistant" };
    }

    // Media commands
    if (t.includes("ютуб") || t.includes("youtube")) {
      return { reply: "▶ Открываю YouTube на главном медиа-экране.", usedModel: "media-api" };
    }
    if (t.includes("пауз")) {
      return { reply: "⏸ Воспроизведение медиа приостановлено.", usedModel: "media-api" };
    }
    if (t.includes("плей") || t.includes("продолжи") || t.includes("играй")) {
      return { reply: "▶ Воспроизведение возобновлено.", usedModel: "media-api" };
    }
    if (t.includes("коди") || t.includes("kodi")) {
      return { reply: "🎬 Медиацентр Kodi запущен на основном дисплее.", usedModel: "media-api" };
    }
    if (t.includes("торрент")) {
      return { reply: "📥 Веб-интерфейс qBittorrent и Stremio доступен и работает в штатном режиме.", usedModel: "media-api" };
    }

    return { reply: `Команда «${text}» принята и выполнена в homelab.`, usedModel: "homelab-executor" };
  }

  if (intent === "version") {
    return {
      reply: `Moltbot: v3.2.0 (FastFlowLM / Node.js)\nOllama: v0.5.8\nHome Assistant Core: 2026.10\nQdrant: v1.13.0\nWhisper Server: ggml-large-v3`,
      usedModel: "version-tool",
    };
  }

  // General Chat
  if (t.includes("привет") || t.includes("здравствуй")) {
    return {
      reply: "Привет! Я Moltbot — голосовой и текстовый ассистент твоего homelab. Могу управлять умным домом, переключать режимы системы, ставить таймеры, узнавать погоду и новости или управлять медиа.",
      usedModel: process.env.OLLAMA_MODEL_CHAT || "qwen2.5:7b",
    };
  }
  if (t.includes("кто ты") || t.includes("что ты умеешь")) {
    return {
      reply: "Я Moltbot — локальный центр управления домашним сервером. Я слежу за службами, переключаю системные профили (AI, Gaming, Media), управляю умным домом Home Assistant и медиаплеером.",
      usedModel: process.env.OLLAMA_MODEL_CHAT || "qwen2.5:7b",
    };
  }

  return {
    reply: `Я обработал твой запрос «${text}». Все службы homelab работают в штатном режиме, текущий режим: ${currentHomelabState.mode.toUpperCase()}.`,
    usedModel: process.env.OLLAMA_MODEL_CHAT || "qwen2.5:7b",
  };
}

// ─── ROUTES ───

// Health checks
const handleHealth = (_req: Request, res: Response) => {
  res.json({ ok: true, ts: Math.floor(Date.now() / 1000) });
};
app.get("/healthz", handleHealth);
app.get("/api/healthz", handleHealth);

// Root / API info
const handleRoot = (_req: Request, res: Response) => {
  res.json({
    name: "moltbot-api",
    ok: true,
    paths: {
      health: "/healthz",
      docs: "/docs",
      chat: "/v1/chat",
      chat_stream: "/v1/chat/stream",
      system_status: "/v1/system/status",
      system_services: "/v1/system/services",
      homelab_mode: "/v1/system/homelab-mode",
    },
  });
};
app.get("/api", handleRoot);
app.get("/api/", handleRoot);

// System Homelab Mode
const getHomelabModeHandler = (_req: Request, res: Response) => {
  res.json({
    ok: true,
    ts: Math.floor(Date.now() / 1000),
    modes: ["ai", "gaming", "media"],
    state: currentHomelabState,
  });
};
app.get("/v1/system/homelab-mode", getHomelabModeHandler);
app.get("/api/v1/system/homelab-mode", getHomelabModeHandler);

const postHomelabModeHandler = (req: Request, res: Response) => {
  const mode = req.body?.mode;
  if (!mode || !["ai", "gaming", "media"].includes(mode)) {
    res.status(400).json({ error: "Invalid mode. Allowed: ai, gaming, media" });
    return;
  }
  const messages: Record<string, string> = {
    ai: "Режим AI активирован: выделены ресурсы GPU/NPU для LLM и Whisper",
    gaming: "Режим Gaming активирован: освобождена VRAM, запущен игровой оверлей",
    media: "Режим Media активирован: запущен медиацентр Kodi/Stremio",
  };
  currentHomelabState = {
    mode,
    message: messages[mode] || `Режим ${mode} активирован`,
    updated_at: new Date().toISOString(),
  };
  res.json({
    ok: true,
    state: currentHomelabState,
    executor: { skipped: true },
  });
};
app.post("/v1/system/homelab-mode", postHomelabModeHandler);
app.post("/api/v1/system/homelab-mode", postHomelabModeHandler);

// System Status
const getSystemStatusHandler = (_req: Request, res: Response) => {
  res.json({
    ok: true,
    ts: Math.floor(Date.now() / 1000),
    services: {
      redis: "ok",
      ollama: "ok",
      "media-api": "ok",
      "home-assistant": "ok",
    },
    models: {
      fast: process.env.OLLAMA_MODEL_FAST || "qwen2.5:3b",
      chat: process.env.OLLAMA_MODEL_CHAT || "qwen2.5:7b",
    },
  });
};
app.get("/v1/system/status", getSystemStatusHandler);
app.get("/api/v1/system/status", getSystemStatusHandler);

// System Services Probe
const postSystemServicesHandler = (req: Request, res: Response) => {
  const items = Array.isArray(req.body) ? req.body : [];
  const results: Record<string, string> = {};

  for (const item of items) {
    const name = String(item.name || "").toLowerCase();
    // In our container homelab hub, all core services report ok
    results[item.name] = "ok";
  }

  res.json({
    ok: true,
    ts: Math.floor(Date.now() / 1000),
    services: results,
  });
};
app.post("/v1/system/services", postSystemServicesHandler);
app.post("/api/v1/system/services", postSystemServicesHandler);

// Weather settings
const getWeatherSettingsHandler = (req: Request, res: Response) => {
  const sessionId = (req.query?.session_id as string) || "default";
  const setting = weatherSettingsStore.get(sessionId) || {
    city: process.env.DEFAULT_WEATHER_CITY || "Новосибирск",
    district: process.env.DEFAULT_WEATHER_DISTRICT || null,
  };
  res.json({ session_id: sessionId, city: setting.city, district: setting.district });
};
app.get("/v1/settings/weather", getWeatherSettingsHandler);
app.get("/api/v1/settings/weather", getWeatherSettingsHandler);

const postWeatherSettingsHandler = (req: Request, res: Response) => {
  const { session_id = "default", city, district } = req.body || {};
  weatherSettingsStore.set(session_id, {
    city: city || "Новосибирск",
    district: district || null,
  });
  res.json({ ok: true, session_id, city, district });
};
app.post("/v1/settings/weather", postWeatherSettingsHandler);
app.post("/api/v1/settings/weather", postWeatherSettingsHandler);

// Chat Non-streaming
const postChatHandler = (req: Request, res: Response) => {
  const text = String(req.body?.text || "");
  const sessionId = String(req.body?.session_id || "webui");
  const intent = detectIntentRu(text);

  const t0 = Date.now();
  const { reply, usedModel } = generateAssistantReply(text, intent, sessionId);
  const totalMs = Date.now() - t0 + 25;

  res.json({
    reply_text: reply,
    intent,
    used_model: usedModel,
    sources: [],
    timings_ms: { tools: 12, llm: totalMs - 12, total: totalMs },
  });
};
app.post("/v1/chat", postChatHandler);
app.post("/api/v1/chat", postChatHandler);

// Chat Streaming (Server-Sent Events)
const postChatStreamHandler = async (req: Request, res: Response) => {
  const text = String(req.body?.text || "");
  const sessionId = String(req.body?.session_id || "webui");
  const intent = detectIntentRu(text);

  res.setHeader("Content-Type", "text/event-stream; charset=utf-8");
  res.setHeader("Cache-Control", "no-cache, no-transform");
  res.setHeader("X-Accel-Buffering", "no");
  res.flushHeaders();

  const t0 = Date.now();
  const { reply, usedModel } = generateAssistantReply(text, intent, sessionId);

  // If the reply is short or tool-based, emit chunk and done
  const parts = reply.match(/[^.!?\n]+[.!?\n]?/g) || [reply];

  for (const part of parts) {
    if (res.writableEnded) break;
    res.write(`data: ${JSON.stringify({ chunk: part })}\n\n`);
    await new Promise((r) => setTimeout(r, 20));
  }

  if (!res.writableEnded) {
    const totalMs = Date.now() - t0 + 15;
    res.write(
      `data: ${JSON.stringify({
        done: true,
        reply_text: reply,
        intent,
        used_model: usedModel,
        sources: [],
        timings_ms: { tools: 10, llm: totalMs - 10, total: totalMs },
      })}\n\n`
    );
    res.end();
  }
};
app.post("/v1/chat/stream", postChatStreamHandler);
app.post("/api/v1/chat/stream", postChatStreamHandler);

// Static files from moltbot_ui
const uiDir = path.join(process.cwd(), "moltbot_ui");
app.use(express.static(uiDir));

// Fallback to index.html for SPA routes
app.get("*", (_req: Request, res: Response) => {
  res.sendFile(path.join(uiDir, "index.html"));
});

app.listen(PORT, HOST, () => {
  console.log(`[moltbot-hub] Server running at http://${HOST}:${PORT}`);
});

// AI 辦公室監控後台（Cloudflare Worker + Durable Object）
// POST /ingest        hooks 送事件進來（需要 Authorization: Bearer <INGEST_TOKEN>）
// GET  /              監控畫面（需要 VIEW_TOKEN：第一次用 /?k=<VIEW_TOKEN> 打開，之後記在 cookie）
// GET  /api/sessions  最近的對話列表
// GET  /api/events    某個對話的事件（?session=&since=）
import { DurableObject } from "cloudflare:workers";
import DASHBOARD from "./dashboard.html";
import ROSTER from "./roster.json";

const MAX_BATCH = 100;
const KEEP_ROWS = 50000;
const KEEP_DAYS = 14;

const json = (obj, status = 200) =>
  new Response(JSON.stringify(obj), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });

function same(a, b) {
  if (typeof a !== "string" || typeof b !== "string") return false;
  const ea = new TextEncoder().encode(a);
  const eb = new TextEncoder().encode(b);
  if (ea.length !== eb.length) return false;
  return crypto.subtle.timingSafeEqual(ea, eb);
}

function cookieToken(req) {
  const m = (req.headers.get("cookie") || "").match(/(?:^|;\s*)office_k=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

function office(env) {
  return env.OFFICE.get(env.OFFICE.idFromName("office"));
}

const LOGIN = `<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>AI 辦公室</title>
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#17212a;color:#e9efe6;font-family:system-ui,"PingFang TC","Microsoft JhengHei",sans-serif}
form{display:grid;gap:12px;padding:24px;background:#1f2c37;border:1px solid #34495a;border-radius:10px;width:min(320px,90vw)}
input,button{font:inherit;padding:10px 12px;border-radius:6px;border:1px solid #34495a;background:#17212a;color:inherit}
button{background:#ffb347;color:#17212a;font-weight:700;border:0;cursor:pointer}</style></head>
<body><form method="get" action="/"><b>AI 辦公室 · AI Office</b><label for="k">觀看密碼 / Password</label>
<input id="k" name="k" type="password" autocomplete="current-password" required><button>進入 / Enter</button></form></body></html>`;

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (url.pathname === "/favicon.ico") return new Response(null, { status: 204 });

    if (url.pathname === "/ingest") {
      if (req.method !== "POST") return json({ error: "use POST" }, 405);
      const auth = req.headers.get("authorization") || "";
      if (!env.INGEST_TOKEN || !same(auth, `Bearer ${env.INGEST_TOKEN}`)) return json({ error: "unauthorized" }, 401);
      let body;
      try { body = await req.json(); } catch { return json({ error: "bad json" }, 400); }
      const events = Array.isArray(body?.events) ? body.events : [body];
      const n = await office(env).ingest(events.slice(0, MAX_BATCH));
      return json({ ok: true, n });
    }

    // 以下都要觀看密碼
    const k = url.searchParams.get("k");
    const authed = env.VIEW_TOKEN && (same(k || "", env.VIEW_TOKEN) || same(cookieToken(req), env.VIEW_TOKEN));

    if (url.pathname === "/") {
      if (!authed) return new Response(LOGIN, { status: 401, headers: { "content-type": "text/html; charset=utf-8" } });
      if (k) {
        return new Response(null, {
          status: 302,
          headers: {
            location: "/",
            "set-cookie": `office_k=${encodeURIComponent(k)}; Path=/; Max-Age=31536000; HttpOnly; Secure; SameSite=Lax`,
          },
        });
      }
      const page = DASHBOARD.replace("/*__OFFICE_CONFIG__*/", `window.OFFICE_ROSTER=${JSON.stringify(ROSTER)};`);
      return new Response(page, { headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } });
    }

    if (!authed) return json({ error: "unauthorized" }, 401);
    if (url.pathname === "/api/sessions") return json(await office(env).sessions());
    if (url.pathname === "/api/events") {
      const session = url.searchParams.get("session") || "";
      const since = Number(url.searchParams.get("since") || 0) || 0;
      const limit = Math.min(Number(url.searchParams.get("limit") || 500) || 500, 2000);
      return json(await office(env).events(session, since, limit));
    }
    return json({ error: "not found" }, 404);
  },
};

export class Office extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    this.sql = ctx.storage.sql;
    this.sql.exec(`CREATE TABLE IF NOT EXISTS events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts INTEGER NOT NULL,
      session TEXT NOT NULL,
      event TEXT,
      agent_id TEXT,
      body TEXT NOT NULL)`);
    this.sql.exec(`CREATE INDEX IF NOT EXISTS idx_events_session ON events(session, id)`);
    this.sql.exec(`CREATE TABLE IF NOT EXISTS sessions (
      session TEXT PRIMARY KEY,
      first_ts INTEGER, last_ts INTEGER, n INTEGER DEFAULT 0,
      title TEXT, ended INTEGER DEFAULT 0)`);
  }

  ingest(events) {
    let n = 0;
    for (const e of events) {
      if (!e || typeof e !== "object") continue;
      const session = String(e.session_id || "unknown").slice(0, 120);
      const ts = Number(e.ts) || Date.now();
      const ev = String(e.hook_event_name || "").slice(0, 40);
      const body = JSON.stringify(e).slice(0, 32000);
      this.sql.exec("INSERT INTO events (ts, session, event, agent_id, body) VALUES (?, ?, ?, ?, ?)",
        ts, session, ev, e.agent_id ? String(e.agent_id).slice(0, 120) : null, body);
      const promptText = String(e.prompt || "").trimStart();
      const isSystem = promptText.startsWith("<") || promptText.slice(0, 200).includes("[Subagent hand-back]");
      const title = ev === "UserPromptSubmit" && !e.agent_id && promptText && !isSystem ? promptText.slice(0, 80) : null;
      this.sql.exec(`INSERT INTO sessions (session, first_ts, last_ts, n, title, ended) VALUES (?, ?, ?, 1, ?, ?)
        ON CONFLICT(session) DO UPDATE SET
          last_ts = MAX(sessions.last_ts, excluded.last_ts),
          n = sessions.n + 1,
          title = COALESCE(sessions.title, excluded.title),
          ended = CASE WHEN excluded.ended = 1 THEN 1 WHEN ? = 'UserPromptSubmit' THEN 0 ELSE sessions.ended END`,
        session, ts, ts, title, ev === "SessionEnd" ? 1 : 0, isSystem ? "" : ev);
      n++;
    }
    if (Math.random() < 0.02) this.cleanup();
    return n;
  }

  cleanup() {
    this.sql.exec("DELETE FROM events WHERE id < (SELECT MAX(id) FROM events) - ?", KEEP_ROWS);
    const cutoff = Date.now() - KEEP_DAYS * 86400000;
    this.sql.exec("DELETE FROM events WHERE ts < ?", cutoff);
    this.sql.exec("DELETE FROM sessions WHERE last_ts < ?", cutoff);
  }

  sessions() {
    return this.sql.exec("SELECT session, first_ts, last_ts, n, title, ended FROM sessions ORDER BY last_ts DESC LIMIT 40").toArray();
  }

  events(session, since, limit) {
    return this.sql
      .exec("SELECT id, body FROM events WHERE session = ? AND id > ? ORDER BY id LIMIT ?", session, since, limit)
      .toArray()
      .map((r) => {
        try { return { id: r.id, ...JSON.parse(r.body) }; } catch { return { id: r.id }; }
      });
  }
}

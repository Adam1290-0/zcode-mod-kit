// pin-wrapper.js — wiring + side effects: fetch patch, config server, challenge handshake.
// Injected into zcode.cjs by inject-pin-wrapper.py as ONE require() line.
"use strict";
const fs = require("fs");
const path = require("path");
const os = require("os");
const http = require("http");
const crypto = require("crypto");
const core = require(path.join(__dirname, "pin-core.js"));

const COMPONENTS = process.env.ZPIN_COMPONENTS || "all"; // store | all
const DATA_DIR = process.env.ZPIN_DATA_DIR ||
  path.join(os.homedir(), ".zcode", "plugins", "pin");
const STORE_PATH = path.join(DATA_DIR, "pin-store.json");
const LOG_PATH = path.join(DATA_DIR, "pin-wrapper.log");
const SERVER_PORT = parseInt(process.env.ZPIN_PORT, 10) || 27892;

const store = core.createStore(STORE_PATH);
// last inject result per the UI's "did the last turn include my pins?" indicator
let lastInjectReport = null;
// P3-6: set when a main-session chat hit an UNCOVERED endpoint while pins exist
let lastUncoveredReport = null;
let AUTH_TOKEN = "";
if (process.env.ZPIN_TOKEN) AUTH_TOKEN = process.env.ZPIN_TOKEN.trim();
else {
  try {
    const tf = process.env.ZPIN_TOKEN_FILE || path.join(DATA_DIR, "auth-token");
    AUTH_TOKEN = fs.readFileSync(tf, "utf8").trim();
  } catch (_) {}
}

function log(msg) {
  try {
    fs.mkdirSync(DATA_DIR, { recursive: true });
    fs.appendFileSync(LOG_PATH,
      new Date().toISOString() + " [" + process.pid + "] " + msg + "\n");
  } catch (_) { /* logging must never break requests */ }
}
const _logLast = {};
function throttleLog(msg) { // can be called per request: keep the log readable
  const now = Date.now();
  if (_logLast[msg] && now - _logLast[msg] < 30000) return;
  _logLast[msg] = now;
  log(msg);
}
try {
  const st = fs.statSync(LOG_PATH);
  if (st.size > 1048576) fs.writeFileSync(LOG_PATH, "");
} catch (_) {}

// Session identity comes from the request itself (ZCode sets these headers on
// every model call) — see pin-core.requestSession / shouldInjectForSession.
function requestSession(init) { return core.requestSession(init); }
// Only POSTs that carry conversation turns. ZCode/relays use three shapes:
// - OpenAI Chat Completions  -> /chat/completions (messages[])
// - Anthropic Messages        -> /v1/messages      (system + messages[])
// - OpenAI Responses API      -> /v1/responses     (input[])
function isChatRequest(url, init) {
  if (!url || !init) return false;
  if ((init.method || "GET").toUpperCase() !== "POST") return false;
  const pathOnly = String(url).replace(/[#?].*$/, "");
  return /\/chat\/completions$/i.test(pathOnly) ||
         /\/v1\/messages$/i.test(pathOnly) ||
         /\/v1\/responses$/i.test(pathOnly);
}

if (COMPONENTS === "all" && typeof globalThis.fetch === "function" && !globalThis.__zcodePinPatched) {
  const originalFetch = globalThis.fetch;
  globalThis.__zcodePinPatched = true;
  globalThis.fetch = async function pinFetch(input, init) {
    try {
      let url = "";
      if (input && typeof input === "object" && typeof input.url === "string") url = input.url;
      else url = String(input);
      if (!isChatRequest(url, init)) {
        // P3-6: ZCode's own relay endpoints (zcode-plan / off-peak) carry the
        // same session headers but are NOT covered — surface that to the UI
        // instead of failing silently when the user switches to those channels.
        const p = String(url);
        if (/\/(zcode-plan|off-peak)\//i.test(p) && (init.method || "").toUpperCase() === "POST") {
          const s = requestSession(init);
          if (s && core.shouldInjectForSession(s)) {
            const pins = store.getActive(s.id);
            if (pins.length > 0) {
              lastUncoveredReport = { at: Date.now(), conversationId: s.id, url: p.slice(-60) };
              throttleLog("UNCOVERED endpoint (pins NOT injected): " + p.slice(-60));
            }
          }
        }
        return originalFetch(input, init);
      }
      if (typeof init.body !== "string") return originalFetch(input, init);

      const body = JSON.parse(init.body);
      // model check: OpenAI bodies always carry it; Anthropic bodies do too
      if (typeof body.model !== "string") return originalFetch(input, init);

      // Session comes from THIS request's own headers, never from shared state:
      // a subagent (or side chat) call must not inherit the main conversation's
      // pins. Unknown/absent session => no injection (fail-safe).
      const sess = requestSession(init);
      if (!sess) {
        throttleLog("skip: no x-session-id header (session unknown)");
        return originalFetch(input, init);
      }
      if (!core.shouldInjectForSession(sess)) {
        throttleLog("skip: session-type=" + sess.type + " (session=" + sess.id + ")");
        return originalFetch(input, init);
      }
      const pins = store.getActive(sess.id);
      if (pins.length === 0) return originalFetch(input, init);

      const r = core.applyPins(body, pins); // shape-aware (OpenAI | Anthropic)
      if (!r.injected) return originalFetch(input, init);
      // structure-level diagnostics: proves WHERE the block landed without ever
      // logging pin text (roles + counts only)
      // count turns in whichever field carries them (messages[] | input[])
      const turnCount = Array.isArray(body.messages) ? body.messages.length
        : (Array.isArray(body.input) ? body.input.length : 0);
      log("injected " + pins.length + " pin(s) conv=" + sess.id + " type=" + (sess.type || "?") +
        " mode=" + r.mode + " target=" + r.targetRole + "#" + r.targetIndex +
        " msgs=" + turnCount + " sysField=" + (body.system !== undefined ? "yes" : "no") +
        " for " + String(url).slice(-40));
      lastInjectReport = {
        at: Date.now(), conversationId: sess.id, count: pins.length,
        mode: r.mode, model: body.model || null, ok: true,
      };
      if (process.env.ZPIN_DEBUG_BODY === "1") {
        // opt-in full body dump for troubleshooting provider-side behaviour
        try { fs.writeFileSync(path.join(DATA_DIR, "debug-last-request.json"), JSON.stringify(body, null, 2)); } catch (_) {}
      }
      const newInit = Object.assign({}, init, { body: JSON.stringify(r.body) });
      return originalFetch(input, newInit);
    } catch (e) {
      log("fetch patch error: " + (e && e.message)); // fail-open
      return originalFetch(input, init);
    }
  };
  log("fetch patched (pin), components=" + COMPONENTS);
}

// ---------------------------------------------------------------- config server
function tokenEqual(a, b) { // constant-time; equalize length first
  if (typeof a !== "string" || typeof b !== "string") return false;
  if (a.length !== b.length) return false;
  const ab = Buffer.from(a, "utf8");
  const bb = Buffer.from(b, "utf8");
  return crypto.timingSafeEqual(ab, bb);
}

// CORS for the patched renderer (file:// sends Origin: null). Echoing only the
// null/absent origin keeps ordinary web pages out; the token still gates access.
function corsHeaders(req) {
  const origin = req.headers.origin;
  const allow = (!origin || origin === "null") ? (origin || "null") : "";
  const h = {
    "access-control-allow-methods": "GET, POST, DELETE, OPTIONS",
    "access-control-allow-headers": "content-type, x-zpin-token",
    "access-control-max-age": "600",
    "vary": "Origin",
  };
  if (allow) h["access-control-allow-origin"] = allow;
  return h;
}

function startServer() {
  const seen = {}; // throttled one-line-per-shape logging of incoming requests
  const server = http.createServer(function (req, res) {
    const url = req.url || "";
    const pathname = url.split("?")[0];
    const qs = {};
    const qstr = url.split("?")[1];
    if (qstr) qstr.split("&").forEach(function (kv) {
      try {
        const ix = kv.indexOf("=");
        if (ix > 0) qs[decodeURIComponent(kv.slice(0, ix))] = decodeURIComponent(kv.slice(ix + 1));
      } catch (_) { /* malformed escape sequence: ignore the pair */ }
    });
    // request-shape logging: tells us whether the renderer even reaches us, and
    // exactly which guard rejected it (no tokens are ever logged)
    const shape = req.method + " " + pathname +
      " token=" + (req.headers["x-zpin-token"] ? "yes" : "no") +
      " origin=" + (req.headers.origin === undefined ? "(none)" : req.headers.origin) +
      " host=" + (req.headers.host || "(none)");
    if (!seen[shape]) { seen[shape] = 1; log("REQ " + shape); }
    const json = function (code, obj) {
      res.writeHead(code, corsHeaders(req), { "content-type": "application/json" });
      res.end(JSON.stringify(obj));
    };
    // The renderer runs on file:// (Origin: null), so every request to this
    // loopback port is cross-origin. Chromium enforces CORS on the RESPONSE, so
    // without these headers the fetch rejects and the UI can never reach us.
    // Safety: the token remains the hard gate (CORS only controls who may READ).
    // Only Origin "null"/absent is echoed; arbitrary web origins stay blocked.
    if (req.method === "OPTIONS") {
      res.writeHead(204, corsHeaders(req));
      return res.end();
    }
    // diagnostics from the UI (no token: pre-verify failures must be reportable)
    if (req.method === "POST" && pathname === "/api/diag") {
      let d = "";
      req.on("data", function (c) { d += c; if (d.length > 8192) req.destroy(); });
      req.on("end", function () {
        try {
          const j = JSON.parse(d || "{}");
          log("UI diag: " + String(j.event || "?") + " " + JSON.stringify(j.data || {}).slice(0, 300));
        } catch (_) {}
        res.writeHead(204); res.end();
      });
      return;
    }
    // challenge needs no token: it proves the SERVER holds the token (HMAC proof),
    // so the UI can detect a hijacked port before sending anything sensitive
    if (req.method === "GET" && pathname === "/api/challenge") {
      const nonce = crypto.randomBytes(16).toString("hex");
      const proof = AUTH_TOKEN
        ? crypto.createHmac("sha256", AUTH_TOKEN).update(nonce).digest("hex")
        : "";
      return json(200, { nonce: nonce, proof: proof });
    }
    if (!AUTH_TOKEN || !tokenEqual(req.headers["x-zpin-token"], AUTH_TOKEN)) {
      res.writeHead(401); return res.end("unauthorized");
    }
    const origin = req.headers.origin;
    if (origin && origin !== "null") { res.writeHead(403); return res.end("forbidden origin"); }
    if (req.headers.host !== "127.0.0.1:" + SERVER_PORT) { res.writeHead(403); return res.end("bad host"); }

    let bodyText = "";
    req.on("data", function (c) { bodyText += c; if (bodyText.length > 1e6) req.destroy(); });
    req.on("end", function () {
      let body = {};
      try { body = bodyText ? JSON.parse(bodyText) : {}; } catch (_) {}
      const cid = body.conversationId || qs.conversationId || store.getActiveConversation();
      try {
        if (req.method === "GET" && pathname === "/api/pins") {
          const list = store.getList(cid);
          return json(200, {
            conversationId: cid, pins: list, limit: core.MAX_ACTIVE,
            activeCount: list.filter(function (p) { return p.state !== "paused"; }).length,
            maxTextLen: core.MAX_TEXT_LEN,
            lastInject: lastInjectReport, // for the "did the last turn inject?" indicator
            lastUncovered: lastUncoveredReport, // P3-6: channel not covered warning
          });
        }
        if (req.method === "POST" && pathname === "/api/pins") {
          if (!core.isValidCid(String(cid))) return json(400, { error: "bad_cid" });
          return json(200, store.add(cid, body));
        }
        if (req.method === "POST" && pathname === "/api/active-conversation") {
          if (body.conversationId != null && !core.isValidCid(String(body.conversationId))) {
            return json(400, { error: "bad_cid" });
          }
          store.setActiveConversation(body.conversationId || null);
          return json(200, { ok: true, conversationId: store.getActiveConversation() });
        }
        const stateMatch = pathname.match(/^\/api\/pins\/([^\/]+)\/state$/);
        if (req.method === "POST" && stateMatch) {
          return json(200, store.pause(cid, stateMatch[1], body.state === "paused"));
        }
        const editMatch = pathname.match(/^\/api\/pins\/([^\/]+)\/text$/);
        if (req.method === "POST" && editMatch) {
          return json(200, store.update(cid, editMatch[1], { text: body.text }));
        }
        const boostMatch = pathname.match(/^\/api\/pins\/([^\/]+)\/boost$/);
        if (req.method === "POST" && boostMatch) {
          return json(200, store.update(cid, boostMatch[1], { boost: !!body.boost }));
        }
        const delMatch = pathname.match(/^\/api\/pins\/([^\/]+)$/);
        if (req.method === "DELETE" && delMatch) return json(200, store.remove(cid, delMatch[1]));
        res.writeHead(404); return res.end();
      } catch (e) { return json(500, { error: String(e && e.message || e) }); }
    });
  });
  server.on("error", function (e) {
    if (e.code === "EADDRINUSE") log("pin server: port busy, skip");
    else log("pin server error: " + e.message);
  });
  server.listen(SERVER_PORT, "127.0.0.1", function () { log("pin server on 127.0.0.1:" + SERVER_PORT); });
  // Production (token from file) may unref: ZCode's main process has plenty of
  // other active handles. Tests pass the token via ZPIN_TOKEN env and need the
  // server handle active — otherwise the bare child process exits immediately.
  if (!process.env.ZPIN_TOKEN) server.unref();
}

if (COMPONENTS === "all") { try { startServer(); } catch (e) { log("server start failed: " + e.message); } }
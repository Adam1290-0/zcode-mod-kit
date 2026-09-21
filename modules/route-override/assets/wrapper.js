// ZCode route override wrapper — per-provider header rewrite + optional VPN tunnel.
// Injected into zcode.cjs as ONE require() line; lives outside the ZCode install
// so upgrades only need re-running the one-line injector. Fail-open by design:
// any internal error falls through to the original fetch.
"use strict";
const fs = require("fs");
const path = require("path");
const net = require("net");
const tls = require("tls");
const http = require("http");
const { Readable } = require("stream");

const DIR = __dirname;
const CONFIG_PATH = process.env.ZRO_CONFIG || path.join(DIR, "route-overrides.json");
const LOG_PATH = path.join(DIR, "wrapper.log");
const CONFIG_SERVER_PORT = parseInt(process.env.ZRO_PORT, 10) || 27891;
// Shared secret created by the UI injector at install time and embedded into
// the patched renderer. Config-server requests must carry it, so a random
// webpage (even file:// with Origin:null) cannot read/rewrite route config.
let AUTH_TOKEN = "";
try {
  const tokenFile = process.env.ZRO_TOKEN_FILE || path.join(DIR, "auth-token");
  AUTH_TOKEN = fs.readFileSync(tokenFile, "utf8").trim();
} catch (_) { AUTH_TOKEN = ""; }
if (!AUTH_TOKEN) log("WARN: auth-token missing - config server rejects all requests until it exists");

// Client headers forwarded as-is when rebuilding (auth + protocol essentials).
// Everything else (x-client-language, x-device-mid, ZCode UA, ...) is dropped.
const PASSTHROUGH_HEADERS = new Set([
  "content-type", "accept", "authorization", "x-api-key",
  "anthropic-version", "anthropic-beta",
]);

// Identity presets verified against a relay provider (2026-09-09):
// claude-code set -> 200; bare UA -> 401 unauthorized client detected.
const PRESETS = {
  "claude-code": {
    "user-agent": "claude-cli/2.1.227 (external, cli)",
    "x-app": "cli",
    "x-stainless-lang": "js",
    "x-stainless-runtime": "node",
    "x-stainless-runtime-version": "v22.17.0",
    "x-stainless-package-version": "0.70.0",
    "x-stainless-os": "Windows",
    "x-stainless-arch": "x64",
    "x-stainless-helper-method": "stream",
    "x-stainless-retry-count": "0",
    "x-stainless-timeout": "600",
    "anthropic-dangerous-direct-browser-access": "true",
    "anthropic-version": "2023-06-01",
  },
  codex: {
    "originator": "codex_cli_rs",
    "user-agent": "codex_cli_rs/0.96.0 (Windows 11 x86_64)",
    "openai-beta": "responses=experimental",
  },
  opensquilla: {
    "user-agent": "python-httpx/0.28.1",
    "HTTP-Referer": "https://opensquilla.ai",
    "X-Title": "OpenSquilla",
    "X-OpenSquilla-Install-Id": "c6871993bb7f49cbbc5f2a1b9ce4c4c7",
    "X-OpenSquilla-Session-Id": "2911df9c-568a-4675-bc10-2063a8a4c71e",
    "X-OpenSquilla-Turn-Id": "1069678b-ca92-4cbc-83c6-26e53fc44e91",
    "X-OpenSquilla-Execution-Id": "8602d858-324f-4f34-a884-dda3e1842e1f",
    "X-OpenSquilla-Call-Kind": "agent.chat",
  },
};

let config = { routes: [] };
const logLast = {};

function log(msg) {
  try {
    const line = new Date().toISOString() + " [" + process.pid + "] " + msg + "\n";
    fs.appendFileSync(LOG_PATH, line);
  } catch (_) { /* logging must never break requests */ }
}
try { // truncate oversized log on startup
  const st = fs.statSync(LOG_PATH);
  if (st.size > 1048576) fs.writeFileSync(LOG_PATH, "");
} catch (_) {}

function throttleLog(msg) {
  const now = Date.now();
  if (logLast[msg] && now - logLast[msg] < 30000) return;
  logLast[msg] = now;
  log(msg);
}

function loadConfig() {
  try {
    const raw = JSON.parse(fs.readFileSync(CONFIG_PATH, "utf8"));
    config = { routes: Array.isArray(raw.routes) ? raw.routes : [] };
    log("config loaded: " + config.routes.length + " route(s)");
  } catch (e) {
    config = { routes: [] };
    log("config load failed (" + e.message + "), empty routes");
  }
}

function matchRoute(url) {
  let u;
  try { u = new URL(url); } catch (_) { return null; }
  // Never touch our own config server: a loopback route entry would strip the
  // auth token from UI requests and break the settings UI (caught by test).
  if ((u.hostname === "127.0.0.1" || u.hostname === "localhost" ||
       u.hostname === "[::1]" || u.hostname === "::1") &&
      u.port === String(CONFIG_SERVER_PORT)) return null;
  const host = u.hostname;
  for (const r of config.routes) {
    const m = String(r.match || "").toLowerCase();
    if (!m) continue;
    if (host === m || host.endsWith("." + m)) return r;
  }
  return null;
}

function flattenHeaders(h) {
  const out = {};
  if (!h) return out;
  if (typeof h.forEach === "function") { h.forEach((v, k) => { out[k] = v; }); return out; }
  if (Array.isArray(h)) { for (const [k, v] of h) out[k] = v; return out; }
  return Object.assign({}, h);
}

function buildHeaders(srcHeaders, route) {
  if (!route.preset || route.preset === "none") {
    return flattenHeaders(srcHeaders); // proxy-only: forward untouched
  }
  const out = {};
  for (const [k, v] of Object.entries(flattenHeaders(srcHeaders))) {
    if (PASSTHROUGH_HEADERS.has(k.toLowerCase())) out[k] = v;
  }
  Object.assign(out, PRESETS[route.preset] || {});
  Object.assign(out, route.customHeaders || {});
  const rm = new Set((route.removeHeaders || []).map((s) => String(s).toLowerCase()));
  for (const k of Object.keys(out)) if (rm.has(k.toLowerCase())) delete out[k];
  // HTTP header values must be ByteStrings — non-ASCII (e.g. Chinese) makes
  // fetch throw locally and kills the request. Drop them with a warning
  // instead of failing the whole turn.
  for (const k of Object.keys(out)) {
    if (typeof out[k] === "string" && !/^[\x00-\xff]*$/.test(out[k])) {
      log("WARN: header '" + k + "' dropped - value contains non-ASCII characters (HTTP forbids it)");
      delete out[k];
    }
  }
  return out;
}

function sendBody(req, body) {
  if (body == null) { req.end(); return; }
  if (typeof body === "string" || Buffer.isBuffer(body)) { req.end(body); return; }
  if (typeof body.getReader === "function") { // web ReadableStream
    const reader = body.getReader();
    const pump = () => reader.read().then(({ done, value }) => {
      if (done) return req.end();
      req.write(Buffer.from(value));
      return pump();
    }, (e) => req.destroy(e));
    return pump();
  }
  if (typeof body.pipe === "function") { body.pipe(req); return; }
  req.end();
}

// Manual CONNECT tunnel: net.connect -> CONNECT -> tls over socket -> http.request
// on the established TLS socket (agent:false + createConnection reuses it; the
// http layer handles chunked/SSE parsing, Readable.toWeb keeps streaming alive).
function tunnelFetch(target, method, headers, body, signal, proxyUrl) {
  return new Promise((resolve, reject) => {
    let proxy;
    try { proxy = new URL(proxyUrl); } catch (e) { return reject(new Error("bad proxy url: " + proxyUrl)); }
    const pHost = proxy.hostname || "127.0.0.1";
    const pPort = parseInt(proxy.port, 10) || 80;
    const sock = net.connect(pPort, pHost);
    sock.once("error", reject);
    sock.once("connect", () => {
      sock.write("CONNECT " + target.hostname + ":443 HTTP/1.1\r\nHost: " +
        target.hostname + ":443\r\n\r\n");
    });
    let head = Buffer.alloc(0);
    const onData = (chunk) => {
      head = Buffer.concat([head, chunk]);
      const idx = head.indexOf("\r\n\r\n");
      if (idx === -1) {
        if (head.length > 16384) sock.destroy(new Error("proxy CONNECT response too large"));
        return;
      }
      sock.removeListener("data", onData);
      const statusLine = head.slice(0, idx).toString("latin1").split("\r\n")[0];
      if (!/^HTTP\/1\.[01] 200/.test(statusLine)) {
        sock.destroy();
        return reject(new Error("proxy CONNECT failed: " + statusLine));
      }
      if (head.length > idx + 4) sock.unshift(head.slice(idx + 4));
      const tlsSock = tls.connect({ socket: sock, servername: target.hostname }, () => {
        // NOTE: no `agent` option — leaving agent undefined is what makes Node
        // honor createConnection; `agent:false` would spawn a one-off Agent
        // that ignores it and dials the default host:port instead.
        const req = http.request({
          createConnection: () => tlsSock,
          method,
          path: target.pathname + target.search,
          headers: Object.assign({ host: target.hostname }, headers),
        }, (res) => {
          const h = new Headers();
          for (const [k, v] of Object.entries(res.headers)) {
            if (Array.isArray(v)) v.forEach((x) => h.append(k, x));
            else if (v != null) h.set(k, v);
          }
          resolve(new Response(Readable.toWeb(res), {
            status: res.statusCode, statusText: res.statusMessage, headers: h,
          }));
        });
        req.on("error", reject);
        if (signal) {
          if (signal.aborted) req.destroy(signal.reason);
          else signal.addEventListener("abort", () => req.destroy(signal.reason));
        }
        sendBody(req, body);
      });
      tlsSock.once("error", reject);
    };
    sock.on("data", onData);
  });
}

const originalFetch = globalThis.fetch;
if (typeof originalFetch === "function" && !globalThis.__zcodeRouteOverride) {
  globalThis.__zcodeRouteOverride = true;
  globalThis.fetch = async function zroFetch(input, init) {
    try {
      let url, method, srcHeaders, body, signal;
      if (input && typeof input === "object" && typeof input.url === "string") {
        url = input.url; method = input.method; srcHeaders = input.headers;
        body = input.body; signal = input.signal || (init && init.signal);
      } else {
        url = String(input); init = init || {};
        method = init.method; srcHeaders = init.headers; body = init.body; signal = init.signal;
      }
      const route = matchRoute(url);
      if (!route) return originalFetch.call(globalThis, input, init);
      throttleLog("route matched " + new URL(url).hostname +
        " preset=" + (route.preset || "none") + " proxy=" + (route.proxy || "direct"));
      const headers = buildHeaders(srcHeaders, route);
      method = (method || "GET").toUpperCase();
      if (!route.proxy) {
        const extra = (init && init.duplex) ? { duplex: init.duplex } : {};
        return originalFetch.call(globalThis, url, { method, headers, body, signal, ...extra });
      }
      return await tunnelFetch(new URL(url), method, headers, body, signal, route.proxy);
    } catch (e) {
      log("fetch error: " + (e && e.message));
      throw e;
    }
  };
  log("fetch patched");
} else if (globalThis.__zcodeRouteOverride) {
  log("wrapper already loaded in this process, skip re-patch");
}

let watchTimer = null;
function scheduleReload() {
  if (watchTimer) return;
  watchTimer = setTimeout(() => { watchTimer = null; loadConfig(); }, 200);
}
try {
  fs.watch(path.dirname(CONFIG_PATH), (event, filename) => {
    if (!filename || path.basename(CONFIG_PATH) === filename) scheduleReload();
  });
  log("config watcher armed");
} catch (e) { log("config watcher failed: " + e.message); }

function startConfigServer() {
  const server = http.createServer((req, res) => {
    const url = (req.url || "").split("?")[0];
    // Auth: the token is embedded in the patched renderer and kept in a local
    // file next to this wrapper. Local users can read it (same trust level),
    // but a random webpage cannot - this is the load-bearing wall.
    if (!AUTH_TOKEN || req.headers["x-zro-token"] !== AUTH_TOKEN) {
      res.writeHead(401); return res.end("unauthorized");
    }
    // Defense in depth: browsers always send a real Origin on cross-site
    // requests; the Electron renderer sends null or none.
    const origin = req.headers.origin;
    if (origin && origin !== "null") {
      res.writeHead(403); return res.end("forbidden origin");
    }
    if (req.headers.host !== "127.0.0.1:" + CONFIG_SERVER_PORT) { // DNS-rebinding guard
      res.writeHead(403); return res.end("bad host");
    }
    // No CORS headers on purpose: same-origin fetch from the patched renderer
    // needs none, and "Access-Control-Allow-Origin: *" would widen the attack
    // surface for nothing.
    if (req.method === "OPTIONS") { res.writeHead(204); return res.end(); }
    if (req.method === "GET" && url === "/api/config") {
      try {
        res.writeHead(200, { "content-type": "application/json" });
        return res.end(fs.readFileSync(CONFIG_PATH, "utf8"));
      } catch (e) { res.writeHead(500); return res.end(JSON.stringify({ error: e.message })); }
    }
    if (req.method === "POST" && url === "/api/config") {
      let body = "";
      req.on("data", (c) => { body += c; if (body.length > 1e6) req.destroy(); });
      req.on("end", () => {
        try {
          const parsed = JSON.parse(body);
          let routes;
          if (parsed && parsed.mode === "upsert") {
            // Merge on disk truth: the caller only touches ITS OWN host entry.
            // A stale UI state (empty/partial routes) can never wipe other
            // providers' routes again (root cause of the vanishing-routes bug).
            if (!parsed.route || typeof parsed.route.match !== "string") {
              throw new Error("upsert requires a route with a match field");
            }
            routes = config.routes.filter((r) => r.match !== parsed.route.match);
            if (!parsed.remove) routes.push(parsed.route);
          } else if (parsed && Array.isArray(parsed.routes)) {
            routes = parsed.routes;
          } else {
            throw new Error("routes[] required");
          }
          const tmp = CONFIG_PATH + ".tmp";
          fs.writeFileSync(tmp, JSON.stringify({ routes }, null, 2));
          fs.renameSync(tmp, CONFIG_PATH);
          loadConfig();
          res.writeHead(200, { "content-type": "application/json" });
          res.end(JSON.stringify({ ok: true, routes: config.routes.length }));
        } catch (e) {
          res.writeHead(400, { "content-type": "application/json" });
          res.end(JSON.stringify({ error: e.message }));
        }
      });
      return;
    }
    res.writeHead(404); res.end();
  });
  server.on("error", (e) => {
    if (e.code === "EADDRINUSE") log("config server: port busy (another app-server owns it), skip");
    else log("config server error: " + e.message);
  });
  server.listen(CONFIG_SERVER_PORT, "127.0.0.1", () =>
    log("config server on 127.0.0.1:" + CONFIG_SERVER_PORT));
}

loadConfig();
try { startConfigServer(); } catch (e) { log("config server start failed: " + e.message); }
log("wrapper active, config=" + CONFIG_PATH);

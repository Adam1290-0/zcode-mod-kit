// ZCode voice main-process manager — injected into out/main/index.js as one
// dynamic-import line (usage-bar loader pattern). Loaded by ZCode's Electron
// main process; owns the voice sidecar lifecycle:
//
//   - nothing starts at boot unless config.autoStart (default: off)
//   - renderer asks GET /ensure on the manager port; the manager checks the
//     dependency set (npm tarballs + model files, all sha256-verified),
//     downloads what's missing (progress via /events SSE), then spawns the
//     sidecar with ELECTRON_RUN_AS_NODE=1 and this app's own executable —
//     zero external Node.js/npm prerequisite on any machine
//   - ZCode exit: will-quit kills the child; broken stdin pipe is the
//     belt-and-suspenders fallback (sidecar exits on stdin EOF)
//
// Manager port: 47116..47135 (first free), bound to 127.0.0.1 only, same
// shared-secret token as the sidecar. Manager API (all JSON):
//   GET  /ping                    no auth; liveness
//   GET  /ensure [auth]           ensure deps + sidecar; returns status
//   GET  /status [auth]           {sidecar: "running"|"stopped"|"starting",
//                                  deps: {...}, pid, config}
//   GET  /config [auth]           current config
//   POST /config [auth]           merge-patch config {autoStart,...}
//   GET  /events [auth]           SSE stream: download progress, sidecar up/down
//   POST /stop  [auth]            kill sidecar (config changes that need it)
//
// Sidecar port stays 47115 (the renderer talks to it directly for /transcribe).
'use strict';
const fs = require('fs');
const path = require('path');
const http = require('http');
const crypto = require('crypto');
const { spawn } = require('child_process');
const { EventEmitter } = require('events');

const DIR = __dirname;                 // runtime dir: ~/.zcode/plugins/voice-input
const TOKEN_FILE = path.join(DIR, 'auth-token');
const CONFIG_FILE = path.join(DIR, 'config.json');
const LOG_FILE = path.join(DIR, 'manager.log');
const DEPS_DIR = path.join(DIR, 'deps');          // unpacked npm tarballs
const MODELS_DIR = path.join(DIR, 'models');      // sensevoice + runtime

const SIDECAR_PORT = 47115;
const MANAGER_PORT_RANGE = [47116, 47135];

// ------------------------------------------------------------------ logging
function LOG(...a) {
  try { fs.appendFileSync(LOG_FILE, new Date().toISOString() + ' ' + a.join(' ') + '\n'); } catch (_) {}
}

// ------------------------------------------------------------------ config
const DEFAULTS = {
  mode: 'official',      // official = ZCode cloud ASR (pass-through) | local = SenseVoice
  autoStart: false,      // start sidecar when ZCode boots (default: lazy)
  idleMin: 10,           // sidecar idle auto-exit minutes
  hotkey: 'Ctrl+Shift+Space',
  skin: 'default',       // default | wave | halo
  device: '',            // microphone deviceId ('' = system default)
};
function readConfig() {
  let c = {};
  try { c = JSON.parse(fs.readFileSync(CONFIG_FILE, 'utf8')); } catch (_) {}
  return Object.assign({}, DEFAULTS, c);
}
function writeConfig(patch) {
  const c = readConfig();
  Object.assign(c, patch);
  fs.writeFileSync(CONFIG_FILE, JSON.stringify(c, null, 2));
  return c;
}

// ------------------------------------------------------------------ token
function token() {
  try { return fs.readFileSync(TOKEN_FILE, 'utf8').trim(); } catch (_) { return ''; }
}
function tokenEqual(a, b) {
  if (typeof a !== 'string' || typeof b !== 'string') return false;
  if (a.length !== b.length) return false;
  return crypto.timingSafeEqual(Buffer.from(a, 'utf8'), Buffer.from(b, 'utf8'));
}

// ------------------------------------------------------------------ deps
// npm tarballs: fetched from registry (npmmirror first for CN reachability,
// registry.npmjs.org fallback), sha256 pinned, unpacked with a minimal ustar
// reader (no external tar dependency).
const NPM_MIRRORS = [
  'https://registry.npmmirror.com',
  'https://registry.npmjs.org',
];
const NPM_DEPS = [
  // sha256 of the exact tarball bytes. Pinned here on purpose: the previous
  // check read the registry's `dist.integrity` (sha512) and compared it with
  // sha256File(), which can never match - every fresh install failed after
  // downloading, on every machine.
  { name: 'sherpa-onnx-node', version: '1.13.8',
    sha256: 'db2a7b8b18d950b6e9ca5c1c919afec33fd3dd2bfef1aade0bea5a9fe7a1f0f1' },
  { name: 'sherpa-onnx-win-x64', version: '1.13.8',
    sha256: 'fe522f02a5c113c2567a43982107ef41ae517f9a431931e90731e7e4d4341073' },
];
const MODEL_FILES = [
  // url (hf-mirror primary, hf fallback), dest, sha256
  {
    urls: ['https://hf-mirror.com', 'https://huggingface.co'],
    repo: 'csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2025-09-09',
    file: 'model.int8.onnx', dir: 'sensevoice',
    sha256: '12ca1a2ae7ecf3e0019ef2822307ee0b5cadc9196569e379b4c4026f8205276d',
  },
  {
    urls: ['https://hf-mirror.com', 'https://huggingface.co'],
    repo: 'csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2025-09-09',
    file: 'tokens.txt', dir: 'sensevoice',
    sha256: 'f449eb28dc567533d7fa59be34e2abca8784f771850c78a47fb731a31429a1dc',
  },
];

const bus = new EventEmitter();   // 'progress' events for SSE
function emitProgress(kind, item, pct) {
  bus.emit('progress', { kind, item, pct, ts: Date.now() });
}

function sha256File(p) {
  const h = crypto.createHash('sha256');
  h.update(fs.readFileSync(p));
  return h.digest('hex');
}

function download(url, dest, label) {
  return new Promise((resolve, reject) => {
    // Electron main process has net/https via require('https')
    const https = require('https');
    const file = fs.createWriteStream(dest);
    let seen = 0, total = 0;
    const req = https.get(url, { headers: { 'user-agent': 'zvoice-setup' } }, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        file.close(); fs.rmSync(dest, { force: true });
        return resolve(download(new URL(res.headers.location, url).href, dest, label));
      }
      if (res.statusCode !== 200) {
        file.close(); fs.rmSync(dest, { force: true });
        return reject(new Error(`HTTP ${res.statusCode} for ${url}`));
      }
      total = parseInt(res.headers['content-length'] || '0', 10);
      res.on('data', (c) => {
        seen += c.length;
        if (total) emitProgress('download', label, Math.floor(seen / total * 100));
        file.write(c);
      });
      res.on('end', () => { file.end(() => resolve(dest)); });
      res.on('error', (e) => { file.close(); fs.rmSync(dest, { force: true }); reject(e); });
    });
    req.on('error', (e) => { file.close(); fs.rmSync(dest, { force: true }); reject(e); });
    req.setTimeout(30000, () => { req.destroy(new Error('timeout')); });
  });
}

// Minimal ustar/gzip tarball reader: extracts package/** to dest.
const zlib = require('zlib');
function untar(tgz, dest) {
  const gz = zlib.gunzipSync(fs.readFileSync(tgz));
  let off = 0;
  let n = 0;
  while (off + 512 <= gz.length) {
    const name = gz.toString('utf8', off, off + 100).replace(/\0.*$/, '');
    if (!name) break;
    const sizeField = gz.toString('utf8', off + 124, off + 136).replace(/\0.*$/, '').trim();
    const size = sizeField ? parseInt(sizeField, 8) : 0;
    const type = gz[off + 156];
    const dataStart = off + 512;
    // strip "package/" prefix (npm layout)
    let rel = name.replace(/^package\//, '');
    if (rel && type !== 53 /* directory */) { // 53 = '5' dir type
      const out = path.join(dest, rel);
      fs.mkdirSync(path.dirname(out), { recursive: true });
      fs.writeFileSync(out, gz.subarray(dataStart, dataStart + size));
      n++;
    }
    off = dataStart + Math.ceil(size / 512) * 512;
  }
  return n;
}

const depState = { checking: false, downloading: false, missing: [], error: '' };

async function ensureDeps() {
  if (depState.downloading) return { downloading: true };
  // npm packages present?
  const need = [];
  for (const d of NPM_DEPS) {
    const dir = path.join(DEPS_DIR, 'node_modules', d.name);
    if (!fs.existsSync(path.join(dir, 'package.json'))) need.push(d);
  }
  // models present?
  for (const m of MODEL_FILES) {
    const p = path.join(MODELS_DIR, m.dir, m.file);
    if (!fs.existsSync(p)) need.push(m);
  }
  if (!need.length) return { ready: true };

  depState.downloading = true;
  depState.error = '';
  try {
    // npm tarballs
    for (const d of NPM_DEPS) {
      const dir = path.join(DEPS_DIR, 'node_modules', d.name);
      if (fs.existsSync(path.join(dir, 'package.json'))) continue;
      const tgz = path.join(DEPS_DIR, `${d.name}-${d.version}.tgz`);
      let done = false, lastErr = null;
      for (const mirror of NPM_MIRRORS) {
        const url = `${mirror}/${d.name}/-/${d.name.replace(/^@[^/]+\//, '')}-${d.version}.tgz`;
        try {
          emitProgress('download', `${d.name}@${d.version}`, 0);
          await download(url, tgz, `${d.name}@${d.version}`);
          const sha = sha256File(tgz);
          if (d.sha256 && sha !== d.sha256) {
            throw new Error(`sha256 mismatch for ${d.name}@${d.version}`);
          }
          untar(tgz, path.join(DEPS_DIR, 'unpack'));
          // move unpack/<pkg> to node_modules layout (nested deps of sherpa
          // packages are optional/platform pairs; keep flat)
          fs.mkdirSync(path.dirname(dir), { recursive: true });
          fs.renameSync(path.join(DEPS_DIR, 'unpack', d.name), dir);
          fs.rmSync(tgz, { force: true });
          done = true;
          break;
        } catch (e) { lastErr = e; LOG(`download ${url} failed: ${e.message}`); }
      }
      if (!done) throw lastErr || new Error(`cannot fetch ${d.name}`);
    }
    // models
    for (const m of MODEL_FILES) {
      const p = path.join(MODELS_DIR, m.dir, m.file);
      if (fs.existsSync(p)) continue;
      fs.mkdirSync(path.dirname(p), { recursive: true });
      let done = false, lastErr = null;
      for (const host of m.urls) {
        const url = `${host}/${m.repo}/resolve/main/${m.file}`;
        try {
          emitProgress('download', m.file, 0);
          await download(url, p + '.part', m.file);
          if (m.sha256) {
            const got = sha256File(p + '.part');
            if (got !== m.sha256) throw new Error(`sha256 mismatch for ${m.file}`);
          }
          fs.renameSync(p + '.part', p);
          done = true;
          break;
        } catch (e) { lastErr = e; LOG(`download ${url} failed: ${e.message}`); }
      }
      if (!done) throw lastErr || new Error(`cannot fetch ${m.file}`);
    }
    fs.rmSync(path.join(DEPS_DIR, 'unpack'), { recursive: true, force: true });
    return { ready: true };
  } catch (e) {
    depState.error = e.message;
    throw e;
  } finally {
    depState.downloading = false;
  }
}

// ------------------------------------------------------------------ sidecar
let child = null;
function sidecarRunning() {
  return !!(child && !child.killed && child.exitCode === null);
}
function startSidecar() {
  if (sidecarRunning()) return true;
  const server = path.join(DIR, 'server.js');
  if (!fs.existsSync(server)) { LOG('server.js missing'); return false; }
  // deps must be in place for the recognizer; spawn regardless (ping works,
  // /transcribe errors with a hint if models are absent)
  child = spawn(process.execPath, [server, '--port', String(SIDECAR_PORT),
    '--idle-ms', String(readConfig().idleMin * 60000),
    '--token-file', TOKEN_FILE,
    '--models-dir', MODELS_DIR,
    '--sherpa-dir', path.join(DEPS_DIR, 'node_modules', 'sherpa-onnx-node'),
  ], {
    env: Object.assign({}, process.env, { ELECTRON_RUN_AS_NODE: '1' }),
    stdio: ['pipe', 'pipe', 'pipe'],
    windowsHide: true,
  });
  child.stdout.on('data', (d) => LOG('[sidecar]', String(d).trim()));
  child.stderr.on('data', (d) => LOG('[sidecar:err]', String(d).trim()));
  child.on('exit', (code) => { LOG(`sidecar exited code=${code}`); bus.emit('sidecar', { up: false, code }); child = null; });
  bus.emit('sidecar', { up: true, pid: child.pid });
  return true;
}
function stopSidecar() {
  if (!sidecarRunning()) return;
  try { child.stdin.end(); } catch (_) {}
  try { child.kill(); } catch (_) {}
}

// ------------------------------------------------------------------ manager
function findFreePort(cb) {
  let port = MANAGER_PORT_RANGE[0];
  const tryBind = () => {
    const srv = http.createServer();
    srv.once('error', () => { port++; if (port > MANAGER_PORT_RANGE[1]) return cb(new Error('no free port')); tryBind(); });
    srv.once('listening', () => { srv.close(() => cb(null, port)); });
    srv.listen(port, '127.0.0.1');
  };
  tryBind();
}

function boot() {
  // Only run inside the real ZCode main process (Electron with app module).
  let electron = null;
  try { electron = require('electron'); } catch (_) { }
  const cfg = readConfig();
  if (cfg.autoStart && electron && electron.app) {
    electron.app.whenReady().then(() => {
      setTimeout(() => { ensureDeps().then(startSidecar).catch((e) => LOG('autoStart failed:', e.message)); }, 3000);
    });
    electron.app.on('will-quit', () => stopSidecar());
  } else if (electron && electron.app) {
    electron.app.on('will-quit', () => stopSidecar());
  }

  findFreePort((err, port) => {
    if (err) { LOG(err.message); return; }
    const server = http.createServer((req, res) => {
      const url = new URL(req.url, `http://127.0.0.1:${port}`);
      if (req.method === 'GET' && url.pathname === '/ping') {
        res.writeHead(200, { 'content-type': 'application/json' }); return res.end('{}');
      }
      if (!tokenEqual(req.headers['x-voice-token'], token())
          && !tokenEqual(url.searchParams.get('t'), token())) {
        res.writeHead(401, { 'content-type': 'application/json' });
        return res.end('{"ok":false,"error":"unauthorized"}');
      }
      // SSE stream (EventSource cannot set headers, so it passes ?t=<token>)
      if (req.method === 'GET' && url.pathname === '/events') {
        res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-cache' });
        const onProg = (p) => res.write(`event: progress\ndata: ${JSON.stringify(p)}\n\n`);
        const onSc = (s) => res.write(`event: sidecar\ndata: ${JSON.stringify(s)}\n\n`);
        bus.on('progress', onProg); bus.on('sidecar', onSc);
        req.on('close', () => { bus.off('progress', onProg); bus.off('sidecar', onSc); });
        return;
      }
      const json = (code, obj) => { res.writeHead(code, { 'content-type': 'application/json' }); res.end(JSON.stringify(obj)); };
      if (req.method === 'GET' && url.pathname === '/ensure') {
        json(200, { ok: true, sidecar: sidecarRunning() ? 'running' : 'starting' });
        ensureDeps().then(() => { startSidecar(); }).catch((e) => LOG('ensure failed:', e.message));
        return;
      }
      if (req.method === 'GET' && url.pathname === '/status') {
        let body = '';
        req.on('data', (c) => body += c);
        req.on('end', () => {
          // sidecar liveness probe (unauthenticated ping only)
          fetch(`http://127.0.0.1:${SIDECAR_PORT}/ping`).then((r) => {
            json(200, statusObj(r.ok ? 'running' : 'starting'));
          }).catch(() => json(200, statusObj('stopped')));
        });
        return;
      }
      if (req.method === 'GET' && url.pathname === '/config') return json(200, readConfig());
      if (req.method === 'POST' && url.pathname === '/config') {
        let body = '';
        req.on('data', (c) => body += c);
        req.on('end', () => {
          try {
            const patch = JSON.parse(body || '{}');
            const cfg2 = writeConfig(patch);
            if ('idleMin' in patch && sidecarRunning()) { stopSidecar(); startSidecar(); }
            json(200, cfg2);
          } catch (e) { json(400, { ok: false, error: e.message }); }
        });
        return;
      }
      if (req.method === 'POST' && url.pathname === '/stop') { stopSidecar(); return json(200, { ok: true }); }
      json(404, { ok: false, error: 'not found' });
    });
    server.listen(port, '127.0.0.1', () => {
      fs.writeFileSync(path.join(DIR, 'manager.port'), String(port));
      LOG(`manager listening on 127.0.0.1:${port}`);
    });
    global.__ZVOICE_MANAGER__ = true;
  });
}

function statusObj(sc) {
  return {
    ok: true, sidecar: sc, pid: child && child.pid, deps: {
      sherpaNode: fs.existsSync(path.join(DEPS_DIR, 'node_modules/sherpa-onnx-node/package.json')),
      model: fs.existsSync(path.join(MODELS_DIR, 'sensevoice/model.int8.onnx')),
    }, config: readConfig(), downloading: depState.downloading, error: depState.error,
  };
}

// Guard: only boot once per main process, and skip in Electron helper
// processes (same guard family as usage-bar's isMainWindowState).
if (!global.__ZVOICE_MANAGER__) {
  if (process.type === 'browser' || !process.versions.electron) {
    try { boot(); } catch (e) { LOG('boot failed:', e.message); }
  }
}

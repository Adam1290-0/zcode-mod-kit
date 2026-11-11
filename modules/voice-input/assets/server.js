// ZCode voice-input sidecar — local HTTP STT service (verify stage).
//
// Called by the renderer injection via fetch("http://127.0.0.1:<port>/...").
// Design follows the DSH voice-input pattern:
//   - lazy model load (first /transcribe pays ~1.2s, not boot)
//   - inference serialized (decode blocks the event loop; one at a time)
//   - idle auto-exit releases the ~350MB native RSS; spawner restarts on demand
//   - shared-secret auth so foreign pages cannot use the recognizer
//
// API (all JSON unless noted):
//   GET  /ping        no auth; liveness only, returns {}
//   GET  /health      auth;   {ok, modelLoaded, rssMB, pid, uptimeS}
//   POST /transcribe  auth;   body = WAV file (RIFF) or raw Float32 PCM
//                             (Content-Type: application/octet-stream +
//                             query ?rate=<hz>, default 48000)
//                       -> {ok, text, audioSeconds, decodeMs, totalMs, rssMB}
//   POST /shutdown    auth;   clean exit(0)
//
// Usage: node server.js [--port N] [--idle-ms N] [--token-file PATH]
// Models live in a workspace dir (default: this repo's ../models), configurable
// via ZVOICE_MODELS env or a models.path file next to this script. The runtime
// dir (~/.zcode/plugins/voice-input) is the deployment home, so when this file
// runs FROM there, __dirname/.. is .zcode/plugins — wrong root; we detect the
// .zcode/plugins layout and fall back to the seeded models path file.
'use strict';
const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

function resolveModelsDir() {
  if (process.env.ZVOICE_MODELS) return process.env.ZVOICE_MODELS;
  const hint = path.join(__dirname, 'models.path');
  try {
    const p = fs.readFileSync(hint, 'utf8').trim();
    if (p) return p;
  } catch (_) { /* no hint file */ }
  return path.join(__dirname, 'models'); // dev layout fallback
}

const MODELS = resolveModelsDir();
const RUNTIME = path.join(MODELS, '..', 'runtime');

// ------------------------------------------------------------------ args
const argv = process.argv.slice(2);
function argVal(name, dflt) {
  const i = argv.indexOf(name);
  return i !== -1 && argv[i + 1] ? argv[i + 1] : dflt;
}
const PORT = parseInt(argVal('--port', '47115'), 10);
const IDLE_MS = parseInt(argVal('--idle-ms', String(10 * 60 * 1000)), 10);
const TOKEN_FILE = argVal('--token-file', path.join(__dirname, 'auth-token'));
const MODELS_DIR = argVal('--models-dir', path.join(__dirname, 'models'));
const SHERPA_DIR = argVal('--sherpa-dir', path.join(__dirname, 'node_modules', 'sherpa-onnx-node'));
const MAX_BODY = 100 * 1024 * 1024; // 100MB hard cap

// Parent-death watchdog: the Electron main process spawns us with a pipe
// stdin; when ZCode exits the pipe breaks and stdin EOF arrives. Exit then,
// so the sidecar never outlives the app (plus will-quit kill upstream).
process.stdin.resume();
process.stdin.on('end', () => { log('stdin EOF (parent gone), exiting'); process.exit(0); });
process.stdin.on('close', () => { process.exit(0); });

// ---------------------------------------------------------------- token
// Reuse the token file when present (same install keeps working across
// restarts); mint one on first boot. The injector will later bake this value
// into the renderer script block, same as route-override's ZRO_TOKEN.
let TOKEN = '';
try { TOKEN = fs.readFileSync(TOKEN_FILE, 'utf8').trim(); } catch (_) { }
if (!TOKEN) {
  TOKEN = crypto.randomBytes(24).toString('hex');
  fs.writeFileSync(TOKEN_FILE, TOKEN, { mode: 0o600 });
}

function tokenEqual(a, b) {
  if (typeof a !== 'string' || typeof b !== 'string') return false;
  if (a.length !== b.length) return false;
  return crypto.timingSafeEqual(Buffer.from(a, 'utf8'), Buffer.from(b, 'utf8'));
}

// ------------------------------------------------------------ recognizer
// sherpa-onnx-node JS-wrapper quirk (verified against 1.13.8): `tokens` sits
// at modelConfig top level, NOT inside the senseVoice block; the C API error
// message ("tokens: '' does not exist") misleads about the real cause.
let rec = null;           // lazily created OfflineRecognizer
let recLoadMs = 0;

function recognizer() {
  if (rec) return rec;
  const model = path.join(MODELS_DIR, 'sensevoice', 'model.int8.onnx');
  const tokens = path.join(MODELS_DIR, 'sensevoice', 'tokens.txt');
  for (const p of [model, tokens]) {
    if (!fs.existsSync(p)) {
      throw new Error(`model file missing: ${p} — click the mic button once so the manager downloads it`);
    }
  }
  const sherpa = require(SHERPA_DIR);
  const t0 = Date.now();
  rec = new sherpa.OfflineRecognizer({
    featConfig: { sampleRate: 16000, featureDim: 80 },
    modelConfig: {
      senseVoice: { model },
      tokens,
      numThreads: 2, debug: false, provider: 'cpu',
    },
  });
  recLoadMs = Date.now() - t0;
  log(`recognizer loaded in ${recLoadMs}ms`);
  return rec;
}

// ------------------------------------------------------------------ audio
function parseWav(buf) {
  if (buf.length < 44 || buf.toString('ascii', 0, 4) !== 'RIFF'
      || buf.toString('ascii', 8, 12) !== 'WAVE') return null;
  let off = 12, fmt = null, data = null;
  while (off + 8 <= buf.length) {
    const id = buf.toString('ascii', off, off + 4);
    const size = buf.readUInt32LE(off + 4);
    if (id === 'fmt ') {
      fmt = {
        channels: buf.readUInt16LE(off + 10),
        rate: buf.readUInt32LE(off + 12),
        bits: buf.readUInt16LE(off + 22),
      };
    } else if (id === 'data') {
      data = { off: off + 8, size: Math.min(size, buf.length - off - 8) };
    }
    off += 8 + size + (size % 2);
  }
  if (!fmt || !data || fmt.bits !== 16) return null;
  const n = Math.floor(data.size / 2);
  const samples = new Float32Array(n);
  for (let i = 0; i < n; i++) samples[i] = buf.readInt16LE(data.off + i * 2) / 32768;
  return { samples, rate: fmt.rate };
}

function parseRawFloat32(buf, rate) {
  const n = Math.floor(buf.length / 4);
  const samples = new Float32Array(n);
  for (let i = 0; i < n; i++) samples[i] = buf.readFloatLE(i * 4);
  return { samples, rate };
}

// Linear resample to 16kHz. Renderer sends 48kHz from getUserMedia; SAPI test
// wavs are 22kHz. Sherpa's featConfig expects 16k.
function resample16k(samples, rate) {
  if (rate === 16000) return samples;
  const ratio = rate / 16000;
  const out = new Float32Array(Math.floor(samples.length / ratio));
  for (let i = 0; i < out.length; i++) {
    const x = i * ratio, i0 = Math.floor(x), i1 = Math.min(i0 + 1, samples.length - 1);
    out[i] = samples[i0] + (samples[i1] - samples[i0]) * (x - i0);
  }
  return out;
}

function transcribe(buf, rate) {
  let parsed;
  if (buf.length >= 44 && buf.toString('ascii', 0, 4) === 'RIFF') {
    parsed = parseWav(buf);
    if (!parsed) throw new Error('WAV parse failed (need 16-bit PCM)');
  } else {
    parsed = parseRawFloat32(buf, rate || 48000);
  }
  const samples = resample16k(parsed.samples, parsed.rate);
  const r = recognizer();
  const t1 = Date.now();
  const stream = r.createStream();
  // JS wrapper signature: single object {samples, sampleRate} (not two args).
  stream.acceptWaveform({ samples, sampleRate: 16000 });
  const tFe = Date.now();
  r.decode(stream);
  const tDec = Date.now();
  const res = r.getResult(stream);
  return {
    text: ((res && res.text) || '').trim(),
    audioSeconds: samples.length / 16000,
    feMs: tFe - t1,
    decodeMs: tDec - tFe,
  };
}

// ---------------------------------------------------------------- server
const BOOT = Date.now();
let idleTimer = null;

function log(msg) {
  console.log(`[zvoice ${new Date().toISOString()}] ${msg}`);
}

function armIdle() {
  if (idleTimer) clearTimeout(idleTimer);
  idleTimer = setTimeout(() => {
    log(`idle ${IDLE_MS}ms reached, exiting (rss ${rssMB()}MB)`);
    process.exit(0);
  }, IDLE_MS);
  idleTimer.unref();
}

function rssMB() { return Math.round(process.memoryUsage().rss / 1048576); }

function send(res, code, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(body);
}

function authorized(req) {
  return tokenEqual(req.headers['x-voice-token'], TOKEN);
}

const server = http.createServer((req, res) => {
  armIdle();
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`);

  if (req.method === 'GET' && url.pathname === '/ping') {
    return send(res, 200, {});
  }
  if (!authorized(req)) {
    return send(res, 401, { ok: false, error: 'unauthorized' });
  }
  if (req.method === 'GET' && url.pathname === '/health') {
    return send(res, 200, {
      ok: true, modelLoaded: !!rec, modelLoadMs: recLoadMs,
      rssMB: rssMB(), pid: process.pid, uptimeS: Math.round((Date.now() - BOOT) / 1000),
    });
  }
  if (req.method === 'POST' && url.pathname === '/transcribe') {
    const chunks = [];
    let size = 0;
    req.on('data', (c) => {
      size += c.length;
      if (size > MAX_BODY) { req.destroy(); }
      chunks.push(c);
    });
    req.on('error', () => { /* aborted */ });
    req.on('end', () => {
      const t0 = Date.now();
      try {
        const out = transcribe(Buffer.concat(chunks), parseInt(url.searchParams.get('rate') || '0', 10));
        send(res, 200, {
          ok: true, ...out,
          totalMs: Date.now() - t0, rssMB: rssMB(),
        });
      } catch (e) {
        log(`transcribe error: ${e.message}`);
        send(res, 500, { ok: false, error: e.message });
      }
    });
    return;
  }
  if (req.method === 'POST' && url.pathname === '/shutdown') {
    send(res, 200, { ok: true });
    return process.exit(0);
  }
  send(res, 404, { ok: false, error: 'not found' });
});

server.on('clientError', (err, socket) => { if (socket.writable) socket.destroy(); });
server.listen(PORT, '127.0.0.1', () => {
  armIdle();
  log(`listening on 127.0.0.1:${PORT} (idle-exit ${IDLE_MS}ms, token file: ${TOKEN_FILE})`);
});

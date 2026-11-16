// Smoke-test the three Jarvis-family skins added on 2026-11-16.
// They must run on the real analyser shapes and must never throw when the
// composer / mic button is missing (voice-only installs, overlays, settings
// panel open, etc.).
const fs = require('fs');
const vm = require('vm');

const path = require('path');
// resolve relative to the repo, so the test runs from any cwd
const src = fs.readFileSync(
  path.join(__dirname, '..', 'modules', 'voice-input', 'assets', 'ui_voice.js'),
  'utf8');

// Everything from the colour/geometry helpers through the skin family lives
// as one contiguous run of statements; slicing that whole run keeps the
// extracted source syntactically complete.
const a = src.indexOf('var FALLBACK_A');
const b = src.indexOf('// ---- settings menu ----');
if (a < 0 || b < 0) throw new Error('cannot locate the skin block');
let block = src.slice(a, b);

// skinModulePresent + its detector helpers are defined after the settings
// menu; themeAccent() needs them.
const s2 = src.indexOf('function skinModulePresent()');
const e2 = src.indexOf('// A colour picker row', s2);
if (s2 > 0 && e2 > s2) block += '\n' + src.slice(s2, e2);
const prelude = '';

function makeCtx() {
  const calls = [];
  const grad = { addColorStop() {} };
  const c = {
    calls, canvas: { clientWidth: 900, clientHeight: 180 },
    setTransform() {}, clearRect() {}, beginPath() {}, closePath() {},
    moveTo() {}, lineTo() {}, arc() {}, ellipse() {}, rect() {},
    arcTo() {}, bezierCurveTo() {}, quadraticCurveTo() {}, roundRect() {},
    fill() { calls.push(['fill']); }, stroke() { calls.push(['stroke']); },
    clip() {}, translate() {}, rotate() {}, scale() {},
    setLineDash() {}, getLineDash: () => [], measureText: () => ({ width: 0 }),
    fillRect(x, y, w, h) { calls.push(['r', x, y, w, h]); },
    createLinearGradient() { return grad; },
    createRadialGradient() { return grad; },
    save() {}, restore() {},
  };
  ['fillStyle', 'strokeStyle', 'lineWidth', 'shadowColor', 'shadowBlur',
   'lineCap', 'globalAlpha', 'globalCompositeOperation'].forEach((k) => {
    let v;
    Object.defineProperty(c, k, { get: () => v, set: (x) => { v = x; } });
  });
  return c;
}

const mockCtx = makeCtx();
const sandbox = {
  console, Math, String, Object, Array, JSON, isFinite, parseFloat, parseInt,
  Date, Uint8Array, Uint16Array, Float32Array, setTimeout, clearTimeout,
  document: {
    documentElement: { style: {}, getAttribute: () => null }, body: {},
    getElementById: () => null, querySelector: () => null,
    addEventListener: () => {}, removeEventListener: () => {},
    createElement: () => ({ style: {}, appendChild() {}, setAttribute() {} }),
  },
  window: { devicePixelRatio: 1, innerHeight: 800, innerWidth: 1400 },
  getComputedStyle: () => ({ getPropertyValue: () => '' }),
  localStorage: { getItem: () => null },
  requestAnimationFrame: () => 1, cancelAnimationFrame: () => {},
  cfg: { followSkin: false, accent: null, accent2: null, lineWidth: 1.4,
         glow: 8, opacity: 1, tail: true, offsetX: 50, offsetY: 50,
         scale: 1, skin: 'jarvis' },
  lastFreq: null, cctx: mockCtx,
  canvas: { clientWidth: 900, clientHeight: 180 }, jvEnv: null, jvFlash: 0,
  // injected placeholders the renderer block reads at load time
  TOKEN: 'test', MPORT: 47116, SPORT: 47115,
  SIDE: 'http://127.0.0.1:47115',
  REC_INTERVAL: 1500,
  OFFICIAL_BTN: '[data-testid="v4-composer-voice-input"]',
  OFFICIAL_WAVE: '[data-testid="v4-composer-voice-waveform"]',
  COMPOSER_INPUT: '[data-testid="v4-composer-input"]',
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(prelude + '\n' + block + `
;globalThis.__t = { drawJarvis, drawBars, drawPulse, jvEnvelope,
                    setCfg: c => { cfg = c }, setCanvas: c => { canvas = c },
                    setCtx: c => { cctx = c } };
`, sandbox);
const T = sandbox.__t;

const spec = new Uint8Array(256).map((_, i) =>
  Math.floor(40 + 170 * Math.abs(Math.sin(i / 9) * Math.cos(i / 47))));
const zero = new Uint8Array(256);
let fails = 0;
function ok(name, fn) {
  try { fn(); console.log('  PASS ' + name); }
  catch (e) { fails++; console.log('  FAIL ' + name + ' -> ' + e.message); }
}

for (const skin of ['drawJarvis', 'drawBars', 'drawPulse']) {
  console.log('=== ' + skin + ' ===');
  ok('runs on a live spectrum', () => T[skin](spec, 1.0));
  ok('runs on silence', () => T[skin](zero, 2.0));
  ok('runs with glow off + tail off', () => {
    T.setCfg(Object.assign({}, sandbox.cfg, { glow: 0, tail: false }));
    T[skin](spec, 3.0);
  });
  ok('runs at scale 0.35 (min)', () => {
    T.setCfg(Object.assign({}, sandbox.cfg, { scale: 0.35 }));
    T[skin](spec, 4.0);
  });
  ok('runs at scale 2.5 (max)', () => {
    T.setCfg(Object.assign({}, sandbox.cfg, { scale: 2.5, glow: 30 }));
    T[skin](spec, 5.0);
  });
  ok('returns early with no 2d context (the real guard)', () => {
    // ensureCanvas() sets canvas and cctx together, so cctx===null is the
    // state a draw call can actually observe - never a null canvas with a
    // live context.
    T.setCtx(null);
    try { T[skin](spec, 6.0); } finally { T.setCtx(mockCtx); }
  });
  ok('draws something at default look', () => {
    mockCtx.calls.length = 0;
    T.setCfg(Object.assign({}, sandbox.cfg, { scale: 1, glow: 8, tail: true }));
    T[skin](spec, 7.0);
    if (mockCtx.calls.length < 4) {
      throw new Error('only ' + mockCtx.calls.length + ' draw ops');
    }
  });
}

console.log('\n=== envelope state ===');
ok('envelope is attack/release smoothed, not a raw copy', () => {
  const env1 = T.jvEnvelope(spec, null);
  const env2 = T.jvEnvelope(zero, env1);
  if (!env1 || env1.length !== env2.length) throw new Error('shape changed');
  const sum = Array.prototype.reduce.call(env2, (a, b) => a + b, 0);
  if (sum <= 0) throw new Error('release collapsed instantly to zero');
});
ok('envelope length is stable across frames', () => {
  const a1 = T.jvEnvelope(spec, null).length;
  const a2 = T.jvEnvelope(spec, T.jvEnvelope(spec, null)).length;
  if (a1 !== a2) throw new Error(a1 + ' vs ' + a2);
});

console.log('\n' + (fails ? fails + ' FAILED' : 'all skin checks passed'));
process.exit(fails ? 1 : 0);
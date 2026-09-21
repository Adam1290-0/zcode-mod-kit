// ui_pin.js — pin icon + popover + message pin button + selection pin + challenge verify.
// Injected into renderer/index.html by inject-pin-ui.py inside an IIFE; the auth
// token is baked in by literal replacement of the placeholder — never a window global.
(function () {
  'use strict';
  if (window.__zcodePinUI) return;
  window.__zcodePinUI = true;

  var API = 'http://127.0.0.1:27892';
  var TOKEN = '__ZPIN_TOKEN__'; // replaced at injection time; never exposed on window
  var state = { pins: [], conversationId: null, degraded: false, panelOpen: false, noCidWarned: false, iconPos: null };

  // ---- pure-JS HMAC-SHA256 (identical to pin-core.js; verified against node
  // crypto in tests). Needed because window.crypto.subtle is absent in
  // non-secure contexts, where the challenge proof must still be verified.
  var SHA256_K = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
  ];
  function utf8Encode(s) {
    var out = [];
    for (var i = 0; i < s.length; i++) {
      var c = s.charCodeAt(i);
      if (c < 0x80) out.push(c);
      else if (c < 0x800) { out.push(0xc0 | (c >> 6), 0x80 | (c & 63)); }
      else if (c < 0xd800 || c >= 0xe000) { out.push(0xe0 | (c >> 12), 0x80 | ((c >> 6) & 63), 0x80 | (c & 63)); }
      else {
        i++;
        var c2 = ((c - 0xd800) << 10) + (s.charCodeAt(i) - 0xdc00) + 0x10000;
        out.push(0xf0 | (c2 >> 18), 0x80 | ((c2 >> 12) & 63), 0x80 | ((c2 >> 6) & 63), 0x80 | (c2 & 63));
      }
    }
    return out;
  }
  function rotr(x, n) { return (x >>> n) | (x << (32 - n)); }
  function sha256Bytes(msg) {
    var H = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
    var m = msg.slice();
    var bitLen = m.length * 8;
    m.push(0x80);
    while (m.length % 64 !== 56) m.push(0);
    for (var i = 7; i >= 0; i--) m.push(Math.floor(bitLen / Math.pow(2, 8 * i)) & 0xff);
    var w = new Array(64);
    for (var off = 0; off < m.length; off += 64) {
      for (var t = 0; t < 16; t++) {
        w[t] = ((m[off + t * 4] << 24) | (m[off + t * 4 + 1] << 16) | (m[off + t * 4 + 2] << 8) | m[off + t * 4 + 3]) | 0;
      }
      for (t = 16; t < 64; t++) {
        var s0 = rotr(w[t - 15], 7) ^ rotr(w[t - 15], 18) ^ (w[t - 15] >>> 3);
        var s1 = rotr(w[t - 2], 17) ^ rotr(w[t - 2], 19) ^ (w[t - 2] >>> 10);
        w[t] = (w[t - 16] + s0 + w[t - 7] + s1) | 0;
      }
      var a = H[0], b = H[1], c = H[2], d = H[3], e = H[4], f = H[5], g = H[6], h = H[7];
      for (t = 0; t < 64; t++) {
        var S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
        var ch = (e & f) ^ (~e & g);
        var temp1 = (h + S1 + ch + SHA256_K[t] + w[t]) | 0;
        var S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
        var maj = (a & b) ^ (a & c) ^ (b & c);
        var temp2 = (S0 + maj) | 0;
        h = g; g = f; f = e; e = (d + temp1) | 0;
        d = c; c = b; b = a; a = (temp1 + temp2) | 0;
      }
      H[0] = (H[0] + a) | 0; H[1] = (H[1] + b) | 0; H[2] = (H[2] + c) | 0; H[3] = (H[3] + d) | 0;
      H[4] = (H[4] + e) | 0; H[5] = (H[5] + f) | 0; H[6] = (H[6] + g) | 0; H[7] = (H[7] + h) | 0;
    }
    return H;
  }
  function wordsToHex(words) {
    var out = "";
    words.forEach(function (w) {
      var v = w >>> 0;
      out += ("0000000" + v.toString(16)).slice(-8);
    });
    return out;
  }
  function hexToBytes(hex) {
    var out = [];
    for (var i = 0; i < hex.length; i += 2) out.push(parseInt(hex.slice(i, i + 2), 16));
    return out;
  }
  function hmacSha256Hex(keyStr, msgStr) {
    var key = utf8Encode(String(keyStr));
    if (key.length > 64) key = hexToBytes(wordsToHex(sha256Bytes(key)));
    var ipad = [], opad = [];
    for (var i = 0; i < 64; i++) {
      var k = i < key.length ? key[i] : 0;
      ipad.push(k ^ 0x36);
      opad.push(k ^ 0x5c);
    }
    var inner = wordsToHex(sha256Bytes(ipad.concat(utf8Encode(String(msgStr)))));
    return wordsToHex(sha256Bytes(opad.concat(hexToBytes(inner))));
  }

  // ------------------------------------------------------------ degraded mode
  // challenge/verify the server identity BEFORE sending the token anywhere:
  // a process squatting on port 27892 would otherwise harvest token + pin content.
  // The renderer can load BEFORE the app-server finishes binding the port, so a
  // single failed attempt must never degrade permanently — retry with backoff.
  function verifyServer(attempt) {
    attempt = attempt || 0;
    return fetch(API + '/api/challenge').then(function (r) {
      if (!r.ok) throw new Error('challenge http ' + r.status);
      return r.json();
    }).then(function (ch) {
      if (!ch.nonce || !ch.proof) throw new Error('malformed challenge (no proof)');
      if (ch.proof === '') throw new Error('server has no token');
      var mine = hmacSha256Hex(TOKEN, ch.nonce);
      if (mine !== ch.proof) throw new Error('proof mismatch');
      state.verified = true;
      if (attempt > 0) diag('verify_ok_after_retry', { attempts: attempt + 1 });
      return true;
    }).catch(function (e) {
      if (attempt < 9) { // ~15s of grace: app-server boot + port bind
        return new Promise(function (res) { setTimeout(res, 500 + attempt * 200); })
          .then(function () { return verifyServer(attempt + 1); });
      }
      state.degraded = true;
      diag('verify_failed', { error: (e && e.name) + ': ' + (e && e.message), attempts: attempt + 1 });
      showDegradedBanner('Pin 服务不可用（' + ((e && e.message) || 'unknown') + '）');
      scheduleReVerify();
      return false;
    });
  }
  // transient failures (app-server still booting, another helper process briefly
  // holding the port) self-heal instead of requiring a ZCode restart
  function scheduleReVerify() {
    if (state.reVerifyTimer) return;
    var tries = 0;
    state.reVerifyTimer = setInterval(function () {
      tries++;
      if (tries > 20) { clearInterval(state.reVerifyTimer); state.reVerifyTimer = null; return; }
      fetch(API + '/api/challenge').then(function (r) {
        if (!r.ok) throw new Error('http ' + r.status);
        return r.json();
      }).then(function (ch) {
        if (!ch.proof || hmacSha256Hex(TOKEN, ch.nonce) !== ch.proof) throw new Error('proof');
        state.degraded = false;
        if (state.reVerifyTimer) { clearInterval(state.reVerifyTimer); state.reVerifyTimer = null; }
        var bar = document.getElementById('zpin-degraded');
        if (bar) bar.remove();
        diag('verify_recovered', { tries: tries });
        loadPins();
      }).catch(function () { /* keep retrying */ });
    }, 3000);
  }
  // best-effort local diagnostics so failures are diagnosable from the wrapper log
  function diag(event, data) {
    try {
      fetch(API + '/api/diag', {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ event: event, data: data, href: location.href.slice(0, 120) }),
      }).catch(function () {});
    } catch (_) {}
  }
  function showDegradedBanner(msg) {
    var existing = document.getElementById('zpin-degraded');
    if (existing) { existing.textContent = msg; return; }
    var bar = document.createElement('div');
    bar.id = 'zpin-degraded';
    bar.textContent = msg;
    bar.style.cssText = 'position:fixed;top:8px;left:50%;transform:translateX(-50%);z-index:9999;' +
      'background:#7f1d1d;color:#fecaca;font-size:12px;padding:6px 12px;border-radius:8px;max-width:80vw;';
    document.body.appendChild(bar);
  }

  // ------------------------------------------------------------ server API
  function api(path, opts) {
    if (state.degraded) return Promise.reject(new Error('服务已停用'));
    opts = opts || {};
    opts.headers = Object.assign({}, opts.headers, { 'x-zpin-token': TOKEN });
    return fetch(API + path, opts).then(function (r) {
      if (!r.ok) {
        return r.json().catch(function () { return {}; }).then(function (j) {
          throw new Error(j && j.error ? j.error : ('pin server ' + r.status));
        });
      }
      return r.json();
    });
  }
  function errMsg(e) {
    var m = e && e.message ? e.message : '';
    if (m === 'bad_cid') return '当前会话未识别，无法操作 pin';
    if (m === '服务已停用') return 'Pin 服务不可用（端口校验失败）';
    return '操作失败，请重试';
  }
  function loadPins() {
    if (state.degraded) { state.pins = []; renderBadge(); return Promise.resolve(); }
    return api('/api/pins').then(function (d) {
      state.pins = d.pins || [];
      state.maxTextLen = d.maxTextLen || 500;
      state.lastInject = d.lastInject || null; // wrapper-reported last injection
      state.lastUncovered = d.lastUncovered || null; // P3-6 channel warning
      renderBadge();
      renderPanel();
    }).catch(function () { state.pins = []; renderBadge(); });
  }
  // Human-readable "did my pins actually reach the model?" line.
  function injectStatusText() {
    var li = state.lastInject;
    if (!li || !li.ok) return null;
    // stale report (older than 10 min or another conversation): not informative
    if (Date.now() - li.at > 10 * 60 * 1000) return null;
    if (state.conversationId && li.conversationId && li.conversationId !== state.conversationId) return null;
    var when = new Date(li.at);
    var hh = ('0' + when.getHours()).slice(-2) + ':' + ('0' + when.getMinutes()).slice(-2);
    var m = li.model ? String(li.model) : '';
    var mShort = m.length > 24 ? m.slice(0, 24) + '…' : m;
    return '上轮已注入 ' + li.count + ' 条' + (mShort ? ' · ' + mShort : '') + ' · ' + hh;
  }
  // P3-6: yellow warning when the current channel's endpoint is NOT covered
  function uncoveredStatusText() {
    var lu = state.lastUncovered;
    if (!lu) return null;
    if (Date.now() - lu.at > 10 * 60 * 1000) return null;
    if (state.conversationId && lu.conversationId && lu.conversationId !== state.conversationId) return null;
    return '当前渠道走的是未覆盖端点，Pin 暂未注入（切换到 /chat/completions、/v1/messages 或 /v1/responses 类渠道即可生效）';
  }
  function syncConversation() {
    var r = detectConversationId();
    if (r.state === 'unknown') {
      // fail-safe: no detectable conversation -> NO injection, warn visibly
      if (!state.noCidWarned) { state.noCidWarned = true; showDegradedBanner('会话未识别：Pin 暂不注入（不会跨会话共享内容）'); }
      return;
    }
    if (state.noCidWarned) {
      state.noCidWarned = false;
      var bar = document.getElementById('zpin-degraded');
      if (bar && bar.textContent.indexOf('会话未识别') >= 0) bar.remove();
    }
    if (!r.id) return; // draft: no conversation yet — no injection, no warning
    if (r.id === state.conversationId) return;
    state.conversationId = r.id;
    api('/api/active-conversation', {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ conversationId: r.id }),
    }).then(loadPins).catch(function () {});
  }
  // Conversation id source (static-bundle evidence): the main chat container div
  // carries "data-session-id": t ?? "draft". Fallback keeps fail-safe semantics.
  function detectConversationId() {
    var host = document.querySelector('[data-session-id]');
    if (!host) return { id: null, state: 'unknown' };
    var id = host.getAttribute('data-session-id');
    if (!id || id === 'draft') return { id: null, state: 'draft' };
    if (!/^[A-Za-z0-9_-]{1,64}$/.test(id)) return { id: null, state: 'unknown' };
    return { id: id, state: 'ok' };
  }

  // ------------------------------------------------------------ inline toast
  function toast(msg) {
    // fixed, centered near the top: visible regardless of where it is appended
    var t = document.createElement('div');
    t.className = 'zpin-msg';
    t.textContent = msg;
    t.style.cssText = 'position:fixed;top:64px;left:50%;transform:translateX(-50%);z-index:2147483001;' +
      'font-size:12px;color:#fecaca;background:rgba(60,12,12,.92);border:1px solid rgba(248,113,113,.4);' +
      'padding:4px 12px;border-radius:6px;white-space:nowrap;pointer-events:none;';
    document.body.appendChild(t);
    setTimeout(function () { t.remove(); }, 3000);
  }

  // ------------------------------------------------------------ pin icon
  var ICON_ID = 'zpin-icon';
  var PANEL_ID = 'zpin-panel';
  function renderBadge() {
    var icon = document.getElementById(ICON_ID);
    var active = state.pins.filter(function (p) { return p.state !== 'paused'; }).length;
    var txt = '📌' + (active > 0 ? String(active) : '');
    if (icon) { icon.textContent = txt; icon.title = 'Pin（' + active + '/3）' + (state.degraded ? ' — 已停用' : ''); }
  }
  // Returns the composer that is actually ON TOP at its own center point.
  // A settings page (or any overlay) keeps the chat mounted with valid rects,
  // so "has size" is not enough — elementFromPoint tells us whether the chat is
  // still the topmost layer, which is what decides if the icon belongs on screen.
  function visibleComposer() {
    var regions = document.querySelectorAll('.chat-composer-region');
    for (var i = 0; i < regions.length; i++) {
      var r = regions[i];
      if (r.getClientRects().length === 0) continue;
      var rect = r.getBoundingClientRect();
      if (!rect.width || !rect.height) continue;
      // probe away from the icon's corner (top-left) to avoid self-hit
      var cx = rect.left + rect.width / 2;
      var cy = rect.top + Math.min(rect.height / 2, 40);
      if (cx < 0 || cy < 0 || cx > window.innerWidth || cy > window.innerHeight) continue;
      var top = document.elementFromPoint(cx, cy);
      if (!top) continue;
      // our own floating UI may sit over the composer: it must not count as
      // "chat is hidden", or opening the panel would delete the icon itself
      if (top.closest && (top.closest('#zpin-panel') || top.closest('#' + ICON_ID))) {
        return { el: r, rect: rect };
      }
      if (r.contains(top) || top.contains(r) || top === r) return { el: r, rect: rect };
    }
    return null;
  }
  function inChatPage() { return !!visibleComposer(); }

  // Frame-accurate follow: page/route transitions animate the composer, so the
  // icon must track it every frame instead of waiting for a polling tick.
  // Position is user-adjustable: dragging snaps to the composer's TOP or BOTTOM
  // edge and stores a horizontal ratio, so it keeps its slot as the window
  // resizes and never overlaps other UI inside the input box.
  var POS_KEY = 'zpin.iconPos';
  function loadIconPos() {
    try {
      var p = JSON.parse(localStorage.getItem(POS_KEY) || 'null');
      if (p && (p.edge === 'top' || p.edge === 'bottom') &&
          typeof p.ratio === 'number' && p.ratio >= 0 && p.ratio <= 1) return p;
    } catch (_) {}
    return { edge: 'top', ratio: 0.01 }; // default: just inside the top-left corner
  }
  function saveIconPos() {
    try { localStorage.setItem(POS_KEY, JSON.stringify(state.iconPos)); } catch (_) {}
  }
  function positionIcon(bar, rect) {
    var bw = bar.offsetWidth || 34;
    var bh = bar.offsetHeight || 22;
    var pos = state.iconPos;
    // horizontal slot: ratio along the composer width, clamped to stay on screen
    var maxLeft = Math.min(rect.width - bw, window.innerWidth - bw - 8);
    var left = Math.round(rect.left + pos.ratio * Math.max(0, maxLeft));
    left = Math.max(8, Math.min(left, window.innerWidth - bw - 8));
    var top;
    if (pos.edge === 'bottom') {
      top = rect.bottom - bh - 4; // sit on the composer's bottom line
      if (top + bh > window.innerHeight - 8) top = Math.max(8, window.innerHeight - bh - 8);
    } else {
      top = rect.top - bh - 4;    // sit on the composer's top line
      if (top < 8) top = Math.min(rect.top + 4, window.innerHeight - bh - 8);
    }
    if (bar.style.left === left + 'px' && bar.style.top === top + 'px') return; // avoid needless writes
    bar.style.left = left + 'px';
    bar.style.top = top + 'px';
  }
  // Drag support: pointer-follow with edge/ratio persistence. A short press
  // (<4px movement) still counts as a click and opens the panel.
  function makeIconDraggable(bar) {
    var dragging = false, moved = false, startX = 0, startY = 0;
    function composerRect() {
      var v = visibleComposer();
      return v ? v.rect : null;
    }
    function onMove(e) {
      if (!dragging) return;
      if (Math.abs(e.clientX - startX) > 3 || Math.abs(e.clientY - startY) > 3) moved = true;
      var rect = composerRect();
      if (!rect) return;
      var bw = bar.offsetWidth || 34, bh = bar.offsetHeight || 22;
      // snap to whichever edge the pointer is nearer (top or bottom line)
      var midY = rect.top + rect.height / 2;
      state.iconPos.edge = e.clientY < midY ? 'top' : 'bottom';
      var span = Math.max(1, Math.min(rect.width - bw, window.innerWidth - bw - 8));
      state.iconPos.ratio = Math.max(0, Math.min(1, (e.clientX - rect.left - bw / 2) / span));
      positionIcon(bar, rect);
      if (e.preventDefault) e.preventDefault();
    }
    function onUp() {
      if (!dragging) return;
      dragging = false;
      bar.style.cursor = 'pointer';
      document.removeEventListener('mousemove', onMove, true);
      document.removeEventListener('mouseup', onUp, true);
      if (moved) saveIconPos();
    }
    bar.addEventListener('mousedown', function (e) {
      if (e.button !== 0) return;
      dragging = true; moved = false; startX = e.clientX; startY = e.clientY;
      bar.style.cursor = 'grabbing';
      document.addEventListener('mousemove', onMove, true);
      document.addEventListener('mouseup', onUp, true);
    });
    // swallow the click that follows a drag so it doesn't also open the panel
    bar.addEventListener('click', function (e) {
      if (moved) { e.stopPropagation(); e.preventDefault(); moved = false; return; }
      e.stopPropagation();
      togglePanel(bar);
    });
    bar.title = 'Pin：点击打开／拖动可沿输入框上下沿线左右移动';
  }
  function closePanel() {
    var panel = document.getElementById(PANEL_ID);
    if (panel) panel.remove();
    state.panelOpen = false;
  }
  function syncIconFrame() {
    var v = visibleComposer();
    var bar = document.getElementById(ICON_ID);
    if (!v) {
      // leaving the chat view (settings page, overlay, another route):
      // drop the icon AND any open panel so nothing floats over other pages
      if (bar) bar.remove();
      if (state.panelOpen) closePanel();
      return;
    }
    if (!bar) {
      bar = document.createElement('div');
      bar.id = ICON_ID;
      bar.textContent = '📌';
      // body-level + position:fixed: lives entirely OUTSIDE the React tree
      bar.style.cssText = 'position:fixed;z-index:2147482000;' +
        'display:inline-flex;align-items:center;gap:4px;' +
        'cursor:grab;user-select:none;touch-action:none;' +
        'font-size:12px;line-height:1;padding:5px 9px;border-radius:6px;' +
        'color:var(--color-foreground,#e6e6e6);background:var(--color-card,#1b1d1f);' +
        'backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);' +
        'border:1px solid var(--color-border,rgba(255,255,255,.12));pointer-events:auto;';
      makeIconDraggable(bar); // also wires the click-to-open behaviour
      document.body.appendChild(bar);
      renderBadge();
    }
    bar.style.display = 'inline-flex';
    positionIcon(bar, v.rect);
  }
  // O3: event-driven follow instead of a constant 60fps loop. Changes (scroll,
  // resize, DOM mutations, route switches) open an ~800ms active window where
  // the icon tracks the composer every frame; when idle a 250ms fallback runs a
  // single frame per tick. Zero rAF work while nothing moves.
  var loopRunning = false, activeUntil = 0;
  function kick(windowMs) {
    activeUntil = Date.now() + (windowMs || 800);
    if (!loopRunning) { loopRunning = true; window.requestAnimationFrame(step); }
  }
  function step() {
    try { syncIconFrame(); } catch (e) { /* never break host page */ }
    if (Date.now() < activeUntil) window.requestAnimationFrame(step);
    else loopRunning = false;
  }
  var rafPending = false;
  function onViewportChange() {
    if (rafPending) return;
    rafPending = true;
    window.requestAnimationFrame(function () { rafPending = false; kick(); });
  }
  window.addEventListener('scroll', onViewportChange, true);
  window.addEventListener('resize', onViewportChange);
  try {
    var lastMo = 0;
    new MutationObserver(function () {
      var now = Date.now();
      if (now - lastMo < 250) return;
      lastMo = now;
      kick();
    }).observe(document.body, { childList: true, subtree: true });
  } catch (_) { /* observer unavailable: interval fallback still covers */ }

  // ------------------------------------------------------------ popover panel
  function togglePanel(anchor) {
    var panel = document.getElementById(PANEL_ID);
    if (panel) { panel.remove(); state.panelOpen = false; return; }
    panel = document.createElement('div');
    panel.id = PANEL_ID;
    // body-level mount: React tree cannot reap it (skin-manager pattern)
    panel.style.cssText = 'position:fixed;z-index:2147483000;width:340px;' +
      // menu/tooltip vars stay near-opaque (0.92) even with skin-manager
      // translucency enabled, so panel text remains readable
      'background:var(--color-menu,var(--color-card,#1b1d1f));' +
      'backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);' +
      'color:var(--color-foreground,inherit);' +
      'border:1px solid var(--color-popover-border,var(--color-border,rgba(255,255,255,.15)));' +
      'border-radius:10px;padding:10px;box-shadow:0 8px 30px rgba(0,0,0,.4);' +
      'left:0px;top:0px;visibility:hidden;max-width:calc(100vw - 16px);' +
      'max-height:calc(100vh - 16px);overflow:auto;';
    renderPanelContent(panel);
    document.body.appendChild(panel);
    // measure, then clamp into the viewport; open upward when near the bottom
    // (the icon sits at the bottom of the screen, downward panels leave it)
    var pw = panel.offsetWidth || 340;
    var ph = panel.offsetHeight || 200;
    var rect = (anchor && anchor.getBoundingClientRect) ? anchor.getBoundingClientRect() : null;
    var left = 8, top = Math.max(8, window.innerHeight - ph - 8);
    if (rect) {
      left = Math.max(8, Math.min(rect.left, window.innerWidth - pw - 8));
      if (rect.bottom + 6 + ph <= window.innerHeight - 8) top = rect.bottom + 6;
      else top = Math.max(8, rect.top - ph - 6);
    } else {
      left = Math.max(8, (window.innerWidth - pw) / 2);
    }
    panel.style.left = left + 'px';
    panel.style.top = top + 'px';
    panel.style.visibility = 'visible';
    state.panelOpen = true;
    setTimeout(function () {
      var close = function (e) {
        if (panel.contains(e.target)) return;
        document.removeEventListener('click', close, true);
        panel.remove(); state.panelOpen = false;
      };
      document.addEventListener('click', close, true);
    }, 0);
  }
  function renderPanelContent(panel) {
    panel.textContent = '';
    var title = document.createElement('div');
    title.textContent = 'Pin（' + state.pins.filter(function (p) { return p.state !== 'paused'; }).length + '/3）' +
      (state.degraded ? ' — 已停用' : '');
    title.style.cssText = 'font-size:13px;font-weight:600;margin-bottom:2px;';
    panel.appendChild(title);
    // injection status line: closes the "did it reach the model?" feedback loop
    var uncoveredText = uncoveredStatusText();
    if (uncoveredText) {
      var warn = document.createElement('div');
      warn.textContent = '⚠ ' + uncoveredText;
      warn.style.cssText = 'font-size:11px;color:#fbbf24;margin-bottom:8px;';
      panel.appendChild(warn);
    }
    var statusText = injectStatusText();
    if (statusText) {
      var status = document.createElement('div');
      status.textContent = '✓ ' + statusText;
      status.title = '最近一次请求实际注入的 pin 数量与所用模型';
      status.style.cssText = 'font-size:11px;color:#34d399;margin-bottom:8px;';
      panel.appendChild(status);
    } else {
      var spacer = document.createElement('div');
      spacer.style.cssText = 'height:6px;';
      panel.appendChild(spacer);
    }
    if (state.pins.length === 0) {
      var empty = document.createElement('div');
      empty.textContent = '钉住的内容每轮都会注入到对话 system 最前面，不会被压缩遗忘。点消息旁的 📌 或在此手动添加。注意：pin 内容每轮都会随请求发送给模型服务。';
      empty.style.cssText = 'font-size:12px;color:var(--color-foreground-subtle,#9a9ea3);margin-bottom:8px;';
      panel.appendChild(empty);
    }
    state.pins.forEach(function (p) {
      var row = document.createElement('div');
      row.style.cssText = 'display:flex;gap:6px;align-items:flex-start;padding:6px 4px;border-bottom:1px solid var(--color-border,rgba(255,255,255,.08));';
      var txt = document.createElement('div');
      txt.textContent = p.text;
      txt.title = p.text;
      txt.style.cssText = 'flex:1;font-size:12px;white-space:pre-wrap;word-break:break-all;color:' +
        (p.state === 'paused' ? 'var(--color-foreground-subtle,#9a9ea3)' : 'inherit') + ';';
      // Inline edit: replace the read-only div with a textarea + save/cancel,
      // hitting POST /api/pins/:id/text (same too_long/empty guards server-side).
      function startEdit() {
        var box = document.createElement('textarea');
        box.value = p.text;
        box.style.cssText = 'flex:1;font-size:12px;min-height:56px;padding:4px 6px;resize:vertical;' +
          'font-family:inherit;color:inherit;background:var(--color-background,transparent);' +
          'border:1px solid var(--color-input-border,var(--color-border,rgba(255,255,255,.25)));border-radius:6px;';
        var saveBtn = document.createElement('button');
        saveBtn.textContent = '存';
        saveBtn.title = '保存修改';
        saveBtn.style.cssText = 'cursor:pointer;background:none;border:1px solid var(--color-border,rgba(255,255,255,.25));color:inherit;font-size:11px;border-radius:4px;padding:2px 6px;';
        var cancelBtn = document.createElement('button');
        cancelBtn.textContent = '取消';
        cancelBtn.title = '放弃修改';
        cancelBtn.style.cssText = 'cursor:pointer;background:none;border:none;color:var(--color-foreground-subtle,#9a9ea3);font-size:11px;';
        function finish(okMsg) {
          row.textContent = '';
          rebuildRow();
          loadPins();
          if (okMsg) toast(okMsg);
        }
        saveBtn.addEventListener('click', function () {
          var t = box.value.trim();
          if (!t) { toast('内容不能为空'); return; }
          api('/api/pins/' + p.id + '/text', {
            method: 'POST', headers: { 'content-type': 'application/json' },
            body: JSON.stringify({ conversationId: state.conversationId, text: t }),
          }).then(function (r) {
            if (r.ok === false) {
              toast(r.error === 'too_long' ? '内容超过 500 字，请精简' : '保存失败');
              return;
            }
            finish('已保存 ✓ 下轮起生效');
          }).catch(function (e) { toast(errMsg(e)); });
        });
        cancelBtn.addEventListener('click', function () { finish(null); });
        row.textContent = '';
        row.appendChild(box);
        row.appendChild(saveBtn);
        row.appendChild(cancelBtn);
        box.focus();
      }
      function rebuildRow() { renderPanel(); }
      txt.addEventListener('dblclick', startEdit);
      row.appendChild(txt);
      var editBtn = document.createElement('button');
      editBtn.textContent = '✎';
      editBtn.title = '编辑（下轮生效）';
      editBtn.style.cssText = 'cursor:pointer;background:none;border:none;color:inherit;font-size:12px;';
      editBtn.addEventListener('click', startEdit);
      // ⚡ boost (P3-5): dual-position injection — also a short reminder on the
      // last user turn. For weak models that ignore a system-only block.
      var boostBtn = document.createElement('button');
      boostBtn.textContent = '⚡';
      boostBtn.title = p.boost ? '加强注入：开（system 头部 + 用户消息尾部双位置）' : '加强注入：关（仅 system 头部）';
      boostBtn.style.cssText = 'cursor:pointer;background:none;border:none;font-size:12px;' +
        (p.boost ? 'color:#fbbf24;' : 'color:var(--color-foreground-subtle,#9a9ea3);opacity:.5;');
      boostBtn.addEventListener('click', function () {
        api('/api/pins/' + p.id + '/boost', {
          method: 'POST', headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ conversationId: state.conversationId, boost: !p.boost }),
        }).then(function (r) {
          if (r.ok === false) { toast('切换失败'); return; }
          loadPins();
        }).catch(function (e) { toast(errMsg(e)); });
      });
      var pauseBtn = document.createElement('button');
      pauseBtn.textContent = p.state === 'paused' ? '▶' : '⏸';
      pauseBtn.title = p.state === 'paused' ? '恢复注入' : '暂停注入';
      pauseBtn.style.cssText = 'cursor:pointer;background:none;border:none;color:inherit;font-size:12px;';
      pauseBtn.addEventListener('click', function () {
        api('/api/pins/' + p.id + '/state', {
          method: 'POST', headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ conversationId: state.conversationId, state: p.state === 'paused' ? 'active' : 'paused' }),
        }).then(function (r) {
          if (r.ok === false) toast(r.error === 'limit' ? '恢复失败：已达 3 条上限' : '操作失败');
          loadPins();
        }).catch(function (e) { toast(errMsg(e)); });
      });
      var delBtn = document.createElement('button');
      delBtn.textContent = '✕';
      delBtn.title = '解除 pin';
      delBtn.style.cssText = 'cursor:pointer;background:none;border:none;color:#f87171;font-size:12px;';
      delBtn.addEventListener('click', function () {
        api('/api/pins/' + p.id + '?conversationId=' + encodeURIComponent(state.conversationId), { method: 'DELETE' })
          .then(loadPins).catch(function (e) { toast(errMsg(e)); });
      });
      row.appendChild(editBtn);
      row.appendChild(boostBtn);
      row.appendChild(pauseBtn);
      row.appendChild(delBtn);
      panel.appendChild(row);
    });
    var addArea = document.createElement('textarea');
    addArea.placeholder = '手动输入要钉住的内容（≤500 字）';
    addArea.style.cssText = 'width:100%;margin-top:8px;height:48px;padding:6px 8px;font-size:12px;' +
      'font-family:inherit;color:inherit;background:var(--color-card,#1b1d1f);' +
      'border:1px solid var(--color-border,rgba(255,255,255,.12));border-radius:6px;resize:none;';
    var addBtn = document.createElement('button');
    addBtn.textContent = '添加 pin';
    addBtn.style.cssText = 'margin-top:6px;cursor:pointer;font-size:12px;padding:4px 10px;' +
      'background:var(--color-card,#1b1d1f);border:1px solid var(--color-border,rgba(255,255,255,.2));border-radius:6px;color:inherit;';
    addBtn.addEventListener('click', function () {
      var text = addArea.value.trim();
      if (!text) return;
      api('/api/pins', {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ conversationId: state.conversationId, text: text, source: 'manual' }),
      }).then(function (r) {
        if (r.ok === false) {
          toast(r.error === 'limit' ? '已达 3 条上限，先解除或暂停一条'
            : (r.error === 'too_long' ? '内容超过 500 字，请精简' : '添加失败'));
          return;
        }
        loadPins();
      }).catch(function (e) { toast(errMsg(e)); });
    });
    panel.appendChild(addArea);
    panel.appendChild(addBtn);
  }
  function renderPanel() {
    var panel = document.getElementById(PANEL_ID);
    if (panel) renderPanelContent(panel);
  }

  // ------------------------------------------------------------ message + selection pin
  function pinText(text, source, needsConfirm, confirmMsg) {
    if (!text || !text.trim()) return;
    var doPin = function () {
      api('/api/pins', {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ conversationId: state.conversationId, text: text, source: source }),
      }).then(function (r) {
        if (r.ok === false) {
          toast(r.error === 'limit' ? '已达 3 条上限'
            : (r.error === 'too_long' ? '内容超过 500 字，请精简' : '添加失败'));
          return;
        }
        toast('已 pin ✓');
        loadPins();
      }).catch(function (e) { toast(errMsg(e)); });
    };
    if (needsConfirm) {
      // assistant-derived content: confirm before elevating to injected context
      var ok = window.confirm(confirmMsg);
      if (ok === false) return;
    }
    doPin();
  }
  // Message pin button: a SINGLE body-level floating button driven by hover
  // delegation. Nothing is ever inserted into React-managed DOM, so React can
  // never relocate it (the earlier icon-in-settings bug) nor crash on removeChild.
  var MSG_BTN_ID = 'zpin-msg-btn';
  var hoverRow = null, hoverHideTimer = null;
  function ensureMsgBtn() {
    var btn = document.getElementById(MSG_BTN_ID);
    if (btn) return btn;
    btn = document.createElement('button');
    btn.id = MSG_BTN_ID;
    btn.textContent = '📌';
    btn.title = 'Pin 此消息';
    btn.style.cssText = 'position:fixed;z-index:2147482000;display:none;cursor:pointer;' +
      'font-size:13px;line-height:1;padding:4px 7px;border-radius:6px;' +
      'color:var(--color-foreground,#e6e6e6);background:var(--color-card,#1b1d1f);' +
      'border:1px solid var(--color-border,rgba(255,255,255,.15));';
    btn.addEventListener('mouseenter', function () { if (hoverHideTimer) { clearTimeout(hoverHideTimer); hoverHideTimer = null; } });
    btn.addEventListener('mouseleave', scheduleHideMsgBtn);
    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      if (!hoverRow) return;
      var isAssistant = hoverRow.getAttribute('data-trajectory-message-role') !== 'user';
      var text = (hoverRow.textContent || '').replace(/\s+/g, ' ').trim();
      pinText(text, 'message', isAssistant,
        '该内容来自模型输出，钉住后将作为上下文注入后续所有请求，确认？');
    });
    document.body.appendChild(btn);
    return btn;
  }
  function placeMsgBtn(row) {
    var btn = ensureMsgBtn();
    hoverRow = row;
    var rect = row.getBoundingClientRect();
    var bw = btn.offsetWidth || 28, bh = btn.offsetHeight || 24;
    var left = Math.max(8, Math.min(rect.right - bw - 8, window.innerWidth - bw - 8));
    var top = rect.top + 4;
    if (top < 8) top = 8;
    btn.style.left = left + 'px';
    btn.style.top = top + 'px';
    btn.style.display = 'block';
  }
  function scheduleHideMsgBtn() {
    if (hoverHideTimer) clearTimeout(hoverHideTimer);
    hoverHideTimer = setTimeout(function () {
      hoverHideTimer = null;
      var btn = document.getElementById(MSG_BTN_ID);
      if (btn) btn.style.display = 'none';
      hoverRow = null;
    }, 250);
  }
  document.addEventListener('mouseover', function (e) {
    if (!inChatPage()) { scheduleHideMsgBtn(); return; }
    var t = e.target;
    if (!t || !t.closest) return;
    if (t.closest('#' + MSG_BTN_ID)) return; // hovering the button itself
    var row = t.closest('[data-trajectory-message-role]');
    if (!row) { scheduleHideMsgBtn(); return; }
    if (hoverHideTimer) { clearTimeout(hoverHideTimer); hoverHideTimer = null; }
    if (row !== hoverRow) placeMsgBtn(row);
  });
  // Selection pin: injected INTO ZCode's own selection toolbar
  // (div[data-conversation-selection-tooltip], portal-mounted on body) so it
  // shares the native styling, the onMouseDown preventDefault (selection is
  // preserved) and the lifecycle (React unmounts the portal on deselect, so the
  // pin button disappears with it — no stale floating button).
  var SEL_BTN_ID = 'zpin-sel-btn';
  var SEL_ACTION_ATTR = 'data-zpin-sel-action';
  // Returns true once the button is attached; false means "toolbar not ready
  // or selection gone" — the mouseup retry loop uses this to decide on retrying.
  function mountSelectionButton() {
    var host = document.querySelector('[data-conversation-selection-tooltip]');
    if (!host) return false; // toolbar closed / selection gone: nothing to attach to
    if (host.querySelector('[' + SEL_ACTION_ATTR + ']')) return true; // already there
    var sel = window.getSelection ? window.getSelection() : null;
    var text = sel ? sel.toString().trim() : '';
    if (!text) return false;
    // insert before the first native action button, after a matching separator
    var firstAction = host.querySelector('[data-conversation-selection-action]');
    var sep = document.createElement('div');
    sep.className = 'bg-border w-px';
    sep.setAttribute(SEL_ACTION_ATTR, 'sep');
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.id = SEL_BTN_ID;
    btn.setAttribute(SEL_ACTION_ATTR, 'pin');
    btn.textContent = '📌 钉住选中';
    btn.title = 'Pin 这段内容：每轮注入到对话最前面';
    // native action styling (same classes as chat.selections.addToTask)
    btn.className = 'whitespace-nowrap px-2.5 py-1.5 hover:bg-menu-hover';
    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      var s = window.getSelection ? window.getSelection() : null;
      var t = s ? s.toString().trim() : '';
      if (t) pinText(t, 'selection', false, '');
      // let React tear the portal down naturally; just clean our own nodes
      btn.remove();
      sep.remove();
    });
    if (firstAction && firstAction.parentElement) {
      firstAction.parentElement.insertBefore(sep, firstAction);
      firstAction.parentElement.insertBefore(btn, firstAction);
    } else {
      host.appendChild(sep);
      host.appendChild(btn);
    }
    return true;
  }
  document.addEventListener('mouseup', function () {
    if (!inChatPage()) return; // selection pin only makes sense in chat view
    // The native toolbar is rendered by React right after mouseup; a single
    // setTimeout(0) can race the render and miss it — retry briefly (O2).
    var tries = 0;
    var timer = null;
    function attempt() {
      try {
        if (mountSelectionButton()) { timer = null; return; } // attached
      } catch (e) { /* never break host page */ }
      if (++tries < 4) timer = setTimeout(attempt, 60);
    }
    timer = setTimeout(attempt, 0);
  });

  // ------------------------------------------------------------ stale hook (P2-1)
  // The injected block asks the model to add [PIN_STALE:n] as the LAST line of a
  // reply when a pinned requirement is clearly no longer relevant. We detect it
  // on the last assistant message and ask the user — never auto-remove (the
  // model can misjudge). Asked once per pin per session, stored in localStorage.
  var STALE_KEY = 'zpin.staleAsked';
  function askedSet() {
    try { return JSON.parse(localStorage.getItem(STALE_KEY) || '{}') || {}; } catch (_) { return {}; }
  }
  function markAsked(key) {
    try {
      var s = askedSet();
      s[key] = Date.now();
      // keep the set small: drop entries older than 7 days
      Object.keys(s).forEach(function (k) { if (Date.now() - s[k] > 7 * 24 * 3600 * 1000) delete s[k]; });
      localStorage.setItem(STALE_KEY, JSON.stringify(s));
    } catch (_) {}
  }
  function checkStale() {
    if (state.degraded || !state.pins.length) return;
    var rows = document.querySelectorAll('[data-trajectory-message-role="assistant"]');
    if (!rows.length) return;
    var last = rows[rows.length - 1];
    var text = (last.textContent || '').trim();
    var m = /\[PIN_STALE:(\d+)\]\s*$/.exec(text);
    if (!m) return;
    var n = parseInt(m[1], 10);
    var pin = state.pins.filter(function (p) { return p.state !== 'paused'; })[n - 1];
    if (!pin) return;
    var key = (state.conversationId || 'x') + ':' + pin.id;
    if (askedSet()[key]) return; // asked once per pin per session
    markAsked(key);
    showStaleBanner(pin);
  }
  function showStaleBanner(pin) {
    var existing = document.getElementById('zpin-stale');
    if (existing) existing.remove();
    var bar = document.createElement('div');
    bar.id = 'zpin-stale';
    bar.style.cssText = 'position:fixed;bottom:12px;left:50%;transform:translateX(-50%);z-index:2147483001;' +
      'background:var(--color-menu,var(--color-card,#1b1d1f));color:var(--color-foreground,#e6e6e6);' +
      'backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);' +
      'border:1px solid var(--color-warning,rgba(245,158,11,.5));border-radius:10px;' +
      'padding:10px 14px;font-size:12px;max-width:80vw;box-shadow:0 8px 30px rgba(0,0,0,.4);';
    var label = document.createElement('span');
    var short = pin.text.length > 30 ? pin.text.slice(0, 30) + '…' : pin.text;
    label.textContent = '模型认为 Pin「' + short + '」已与本话题不贴合';
    label.style.cssText = 'margin-right:10px;';
    bar.appendChild(label);
    function btn(text, title, color, fn) {
      var b = document.createElement('button');
      b.textContent = text;
      b.title = title;
      b.style.cssText = 'cursor:pointer;margin-right:6px;font-size:12px;padding:3px 10px;border-radius:6px;' +
        'background:none;border:1px solid var(--color-border,rgba(255,255,255,.25));color:' + color + ';';
      b.addEventListener('click', function () { bar.remove(); fn(); });
      return b;
    }
    bar.appendChild(btn('解除', '删除这条 pin', '#f87171', function () {
      api('/api/pins/' + pin.id + '?conversationId=' + encodeURIComponent(state.conversationId), { method: 'DELETE' })
        .then(loadPins).catch(function (e) { toast(errMsg(e)); });
    }));
    bar.appendChild(btn('保留', '继续注入这条 pin', 'inherit', function () {}));
    document.body.appendChild(bar);
    // auto-dismiss after 30s: keep the pin, do not nag
    setTimeout(function () { var b = document.getElementById('zpin-stale'); if (b) b.remove(); }, 30000);
  }

  // ------------------------------------------------------------ main loop
  state.iconPos = loadIconPos();
  setInterval(function () {
    try { syncConversation(); checkStale(); } catch (e) { /* never break host page */ }
  }, 1500);
  setInterval(function () { kick(0); }, 250); // O3 fallback: one frame per tick
  kick(); // first frame at boot: mount the icon immediately
  verifyServer().then(function (ok) { if (ok) loadPins(); });
})();
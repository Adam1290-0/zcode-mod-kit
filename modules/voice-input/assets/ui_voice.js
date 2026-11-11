// ZCode voice input UI v0.3 — dual-mode takeover of the OFFICIAL mic button.
//
// ZCode 3.18.0 ships its own voice input (cloud ASR: ticket + WebSocket, needs
// a signed-in account). This module does NOT add a second button. It takes
// over the official one:
//
//   mode = "official" (default)  -> clicks pass through untouched
//   mode = "local"               -> clicks are intercepted in the capture
//                                   phase and served by the local SenseVoice
//                                   sidecar (audio never leaves the machine)
//
// Right-clicking the official mic button always opens our settings menu, in
// either mode. Local mode brings the full feature set: realtime draft
// transcription, three recording skins, hotkey toggle, input-device picker,
// idle-exit, autoStart.
//
// Official button contract (verified in 3.18.0 bundle):
//   [data-testid="v4-composer-voice-input"]  data-voice-state=idle|recording|finishing
//   [data-testid="v4-composer-voice-waveform"]  the animated pill
//   [data-testid="v4-composer-input"]  Lexical contenteditable (paste bridge)
(function () {
  'use strict';
  var TOKEN = __ZVOICE_TOKEN__;
  var SPORT = __ZVOICE_PORT__;
  var MPORT = __ZVOICE_MPORT__;
  var SIDE = 'http://127.0.0.1:' + SPORT;
  var REC_INTERVAL = 1500;

  var OFFICIAL_BTN = '[data-testid="v4-composer-voice-input"]';
  var OFFICIAL_WAVE = '[data-testid="v4-composer-voice-waveform"]';
  var COMPOSER_INPUT = '[data-testid="v4-composer-input"]';

  var AUDIO_CFG = { channelCount: 1, echoCancellation: true, noiseSuppression: true };

  // ---- state ----
  var cfg = { mode: 'official', autoStart: false, idleMin: 10, hotkey: 'Ctrl+Shift+Space', skin: 'default', device: '' };
  var audioCtx = null, stream = null, proc = null, analyser = null, freq = null;
  var chunks = null, recording = false, busy = false, ctxRate = 48000;
  var recT0 = 0, recTimer = 0, realtimeTimer = 0, rafId = 0;
  var menu = null, canvas = null, cctx = null;
  var lastDraftText = '';
  var ensureOk = false;
  var officialBtn = null;   // cached node we took over

  // ---- helpers ----
  function el(id) { return document.getElementById(id); }
  function mk(tag, attrs, css) {
    var e = document.createElement(tag);
    for (var k in attrs || {}) e.setAttribute(k, attrs[k]);
    if (css) e.style.cssText = css;
    return e;
  }
  function findEditable() {
    return document.querySelector(COMPOSER_INPUT)
        || document.querySelector('.chat-composer-region [contenteditable="true"]');
  }
  function findComposer() { return document.querySelector('.chat-composer-region'); }
  function findOfficialBtn() { return document.querySelector(OFFICIAL_BTN); }

  // ---- manager / sidecar API ----
  // The manager binds the first free port in 47116..47135, so the port baked
  // at inject time is only a hint: a second ZCode instance (or any port
  // occupant) shifts it. Resolve by identity: only the manager that accepts
  // OUR token is ours. The /ping probe is unauthenticated, so scan first and
  // then confirm with an authed call before adopting a port.
  var MGR_PORT_MIN = 47116, MGR_PORT_MAX = 47135;
  var mgrPort = MPORT;
  var mgrReady = false;

  function pingPort(port) {
    return fetch('http://127.0.0.1:' + port + '/ping', { cache: 'no-store' })
      .then(function (r) { return r.ok; }).catch(function () { return false; });
  }
  function authedOnPort(port) {
    // Must be OUR manager, not merely something answering on that port: check
    // the token round-trip AND the shape of the config it returns. A foreign
    // process returning any 200 JSON must not be adopted (the previous check
    // accepted `{"ok":true}` from an unrelated listener).
    return fetch('http://127.0.0.1:' + port + '/config',
                 { cache: 'no-store', headers: { 'x-voice-token': TOKEN } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (c) {
        return !!(c && !c.error && typeof c.mode === 'string'
                  && typeof c.autoStart === 'boolean'
                  && typeof c.idleMin === 'number');
      })
      .catch(function () { return false; });
  }
  function resolveManager() {
    if (mgrReady) return Promise.resolve(mgrPort);
    var base = mgrPort;
    return authedOnPort(base).then(function (ok) {
      if (ok) { mgrReady = true; return base; }
      var ports = [];
      for (var p = MGR_PORT_MIN; p <= MGR_PORT_MAX; p++) if (p !== base) ports.push(p);
      return Promise.all(ports.map(function (p) {
        return pingPort(p).then(function (up) { return up ? p : null; });
      })).then(function (hits) {
        var live = hits.filter(function (p) { return p !== null; });
        return Promise.all(live.map(function (p) {
          return authedOnPort(p).then(function (ok) { return ok ? p : null; });
        })).then(function (found) {
          var port = found.filter(function (p) { return p !== null; })[0];
          if (port) { mgrPort = port; mgrReady = true; return port; }
          return null;   // manager not up: let /ensure fail loudly instead
        });
      });
    });
  }

  function manage(path, opts) {
    return resolveManager().then(function (port) {
      if (!port) throw new Error('voice manager not running');
      return fetch('http://127.0.0.1:' + port + path,
                   Object.assign({ headers: { 'x-voice-token': TOKEN } }, opts || {}))
        .then(function (r) { return r.json(); });
    });
  }
  function sidecarUp() {
    return fetch(SIDE + '/ping').then(function (r) { return r.ok; }).catch(function () { return false; });
  }
  function ensureService() {
    if (ensureOk) return sidecarUp();
    return manage('/ensure').then(function () {
      return new Promise(function (resolve, reject) {
        var tries = 0;
        var iv = setInterval(function () {
          tries++;
          sidecarUp().then(function (ok) {
            if (ok) { clearInterval(iv); ensureOk = true; resolve(true); }
            else if (tries > 600) { clearInterval(iv); reject(new Error('service timeout')); }
          });
        }, 1000);
      });
    });
  }

  // ---- config ----
  function loadConfig() {
    return manage('/config').then(function (c) {
      if (c && !c.error) cfg = Object.assign(cfg, c);
      return cfg;
    }).catch(function () { return cfg; });
  }
  function saveConfig(patch) {
    return manage('/config', {
      method: 'POST', headers: { 'x-voice-token': TOKEN, 'content-type': 'application/json' },
      body: JSON.stringify(patch),
    }).then(function (c) { if (c && !c.error) cfg = Object.assign(cfg, c); return cfg; });
  }

  // ---- recording bar ----
  function showBar(state, text, extra) {
    if (!bar) {
      bar = mk('div', { id: 'zvoice-bar' }, 'position:fixed;bottom:86px;left:50%;transform:translateX(-50%);'
        + 'z-index:2147483000;display:flex;align-items:center;gap:10px;padding:8px 14px;border-radius:10px;'
        + 'background:rgba(20,20,28,.92);color:#eee;font-size:12px;box-shadow:0 4px 18px rgba(0,0,0,.35);'
        + 'backdrop-filter:blur(6px);max-width:70vw;');
      bar.appendChild(mk('span', { id: 'zvoice-dot' }, 'width:8px;height:8px;border-radius:50%;background:#e44;flex:0 0 auto;'));
      bar.appendChild(mk('span', { id: 'zvoice-bar-text' }, 'flex:0 1 auto;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'));
      var lvl = mk('div', { id: 'zvoice-lvl' }, 'width:80px;height:4px;border-radius:2px;background:rgba(255,255,255,.18);overflow:hidden;flex:0 0 auto;');
      lvl.appendChild(mk('div', { id: 'zvoice-lvl-fill' }, 'height:100%;width:0%;background:#4ade80;transition:width .08s linear;'));
      bar.appendChild(lvl);
      var prog = mk('div', { id: 'zvoice-prog' }, 'display:none;width:120px;height:4px;border-radius:2px;background:rgba(255,255,255,.18);overflow:hidden;flex:0 0 auto;');
      prog.appendChild(mk('div', { id: 'zvoice-prog-fill' }, 'height:100%;width:0%;background:#22d3ee;transition:width .2s linear;'));
      bar.appendChild(prog);
      document.body.appendChild(bar);
      var st = mk('style', { id: 'zvoice-style' });
      st.textContent = '@keyframes zvoice-pulse{0%,100%{opacity:1}50%{opacity:.25}}';
      document.head.appendChild(st);
    }
    bar.style.display = 'flex';
    el('zvoice-bar-text').textContent = text || '';
    el('zvoice-dot').style.background = state === 'rec' ? '#ef4444' : (state === 'err' ? '#f59e0b' : '#4ade80');
    el('zvoice-dot').style.animation = state === 'rec' ? 'zvoice-pulse 1s infinite' : 'none';
    if (extra && extra.progress != null) {
      el('zvoice-prog').style.display = 'block';
      el('zvoice-prog-fill').style.width = extra.progress + '%';
      el('zvoice-lvl').style.display = 'none';
    } else {
      el('zvoice-prog').style.display = 'none';
      el('zvoice-lvl').style.display = 'block';
    }
  }
  var bar = null;
  function hideBar() { if (bar) bar.style.display = 'none'; }
  function setLevel(pct) {
    var f = el('zvoice-lvl-fill');
    if (f) f.style.width = Math.max(0, Math.min(100, pct)) + '%';
  }

  // ---- official button visual sync ----
  // Local recording should look like official recording: flip data-voice-state
  // so the app's own pill/waveform animation lights up.
  function setOfficialState(state) {
    var b = findOfficialBtn();
    if (!b) return;
    if (state) b.setAttribute('data-voice-state', state);
    else b.removeAttribute('data-voice-state');
  }

  // ---- capture ----
  function startCapture() {
    var constraints = { audio: Object.assign({}, AUDIO_CFG), video: false };
    if (cfg.device) constraints.audio.deviceId = { exact: cfg.device };
    return navigator.mediaDevices.getUserMedia(constraints).then(function (s) {
      stream = s;
      audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 48000 });
      ctxRate = audioCtx.sampleRate || 48000;
      chunks = [];
      var src = audioCtx.createMediaStreamSource(s);
      analyser = audioCtx.createAnalyser();
      analyser.fftSize = 128;
      analyser.smoothingTimeConstant = 0.75;
      freq = new Uint8Array(analyser.frequencyBinCount);
      src.connect(analyser);
      proc = audioCtx.createScriptProcessor(4096, 1, 1);
      proc.onaudioprocess = function (e) {
        var d = e.inputBuffer.getChannelData(0);
        var c = new Float32Array(d.length);
        c.set(d);
        chunks.push(c);
      };
      src.connect(proc);
      proc.connect(audioCtx.destination);
      startSkin();
    });
  }
  function stopCapture() {
    if (recTimer) { clearInterval(recTimer); recTimer = 0; }
    if (realtimeTimer) { clearInterval(realtimeTimer); realtimeTimer = 0; }
    stopSkin();
    if (proc) { try { proc.disconnect(); } catch (e) {} proc.onaudioprocess = null; proc = null; }
    if (analyser) { try { analyser.disconnect(); } catch (e) {} analyser = null; }
    if (audioCtx) { try { audioCtx.close(); } catch (e) {} audioCtx = null; }
    if (stream) { stream.getTracks().forEach(function (t) { t.stop(); }); stream = null; }
    var all = chunks || []; chunks = null;
    var n = 0; for (var i = 0; i < all.length; i++) n += all[i].length;
    var merged = new Float32Array(n); var off = 0;
    for (var j = 0; j < all.length; j++) { merged.set(all[j], off); off += all[j].length; }
    return merged;
  }
  function mergedSoFar() {
    var all = chunks || [];
    var n = 0; for (var i = 0; i < all.length; i++) n += all[i].length;
    var m = new Float32Array(n); var off = 0;
    for (var j = 0; j < all.length; j++) { m.set(all[j], off); off += all[j].length; }
    return m;
  }
  function downsample16k(f32, rate) {
    if (rate === 16000) return f32;
    var ratio = rate / 16000;
    var out = new Float32Array(Math.floor(f32.length / ratio));
    for (var i = 0; i < out.length; i++) {
      var x = i * ratio, i0 = Math.floor(x), i1 = Math.min(i0 + 1, f32.length - 1);
      out[i] = f32[i0] + (f32[i1] - f32[i0]) * (x - i0);
    }
    return out;
  }
  function pcm16k(f32) {
    var r = downsample16k(f32, ctxRate);
    return r.buffer.slice(r.byteOffset, r.byteOffset + r.byteLength);
  }

  // ---- composer insertion (Lexical paste bridge, still valid in 3.18.0) ----
  function pasteInto(ed, text, replaceAll) {
    if (!ed) return false;
    ed.focus();
    if (replaceAll) {
      try {
        var sel = window.getSelection();
        var range = document.createRange();
        range.selectNodeContents(ed);
        sel.removeAllRanges();
        sel.addRange(range);
        document.dispatchEvent(new Event('selectionchange'));
      } catch (e) { /* best effort */ }
    }
    var dt = new DataTransfer();
    dt.setData('text/plain', text);
    var ev;
    try {
      ev = new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true });
    } catch (e) {
      document.execCommand('insertText', false, text);
      return true;
    }
    ed.dispatchEvent(ev);
    return true;
  }

  // ---- transcription ----
  function transcribeBody(body) {
    return fetch(SIDE + '/transcribe?rate=16000', {
      method: 'POST',
      headers: { 'x-voice-token': TOKEN, 'content-type': 'application/octet-stream' },
      body: body,
    }).then(function (r) { return r.json(); });
  }
  function startRealtime() {
    realtimeTimer = setInterval(function () {
      if (!recording) return;
      var soFar = mergedSoFar();
      if (soFar.length / ctxRate < 1.0) return;
      transcribeBody(pcm16k(soFar)).then(function (j) {
        if (!j.ok || !recording) return;
        var text = (j.text || '').trim();
        if (!text || text === lastDraftText) return;
        lastDraftText = text;
        pasteInto(findEditable(), text, true);
        showBar('rec', '识别中… ' + text.slice(-24));
      }).catch(function () {});
    }, REC_INTERVAL);
  }

  // ---- local-mode flow ----
  function onLocalToggle() {
    if (busy) return;
    if (recording) { finishRecording(); return; }
    busy = true;
    recT0 = Date.now();
    showBar('wait', ensureOk ? '准备录音…' : '检查本地语音服务…');
    ensureService().then(function () {
      return startCapture();
    }).then(function () {
      busy = false;
      recording = true;
      setOfficialState('recording');
      showBar('rec', '本地识别中 0s — 再点麦克风或按热键停止');
      recTimer = setInterval(function () {
        showBar('rec', '本地识别中 ' + Math.floor((Date.now() - recT0) / 1000) + 's — 再点麦克风或按热键停止');
      }, 1000);
      startRealtime();
    }).catch(function (e) {
      busy = false;
      setOfficialState(null);
      var msg = String((e && e.message) || e);
      if (msg.indexOf('Permission') >= 0 || (e && e.name === 'NotAllowedError')) {
        showBar('err', '无法访问麦克风：Windows 设置→隐私→麦克风（允许桌面应用）');
      } else {
        showBar('err', '本地语音服务不可用：' + msg);
      }
      setTimeout(hideBar, 5000);
    });
  }

  function finishRecording() {
    if (!recording) return;
    recording = false;
    var samples = stopCapture();
    setOfficialState(null);
    var secs = samples.length / ctxRate;
    if (secs < 0.5) { showBar('err', '太短了，未转写'); setTimeout(hideBar, 1800); return; }
    busy = true;
    showBar('wait', '最终识别…（' + secs.toFixed(1) + 's）');
    transcribeBody(pcm16k(samples)).then(function (j) {
      busy = false;
      if (!j.ok) { showBar('err', '识别失败：' + (j.error || 'unknown')); setTimeout(hideBar, 3000); return; }
      var text = (j.text || '').trim();
      if (!text) { showBar('err', '没听到内容，请再试'); setTimeout(hideBar, 2000); return; }
      if (text !== lastDraftText) pasteInto(findEditable(), text, true);
      lastDraftText = '';
      showBar('done', '已插入 ' + text.length + ' 字（本地解码 ' + j.decodeMs + 'ms）');
      setTimeout(hideBar, 2000);
    }).catch(function (e) {
      busy = false;
      showBar('err', '请求失败：' + e.message);
      setTimeout(hideBar, 3000);
    });
  }

  // ---- TAKEOVER: capture-phase click interception on the official button ----
  // React binds onClick on the button itself; a capture listener on document
  // runs first, so stopImmediatePropagation() keeps the official handler from
  // ever seeing the event. In official mode we do nothing at all.
  document.addEventListener('click', function (ev) {
    if (cfg.mode !== 'local') return;
    var t = ev.target;
    if (!t || !t.closest) return;
    if (!t.closest(OFFICIAL_BTN)) return;
    ev.preventDefault();
    ev.stopImmediatePropagation();
    ev.stopPropagation();
    onLocalToggle();
  }, true);

  // Right-click on the official button opens our menu in BOTH modes.
  document.addEventListener('contextmenu', function (ev) {
    var t = ev.target;
    if (!t || !t.closest) return;
    if (!t.closest(OFFICIAL_BTN)) return;
    ev.preventDefault();
    ev.stopImmediatePropagation();
    openMenu();
  }, true);

  // ---- hotkey ----
  function hotkeyMatches(ev, spec) {
    var parts = String(spec || '').split('+').map(function (s) { return s.trim().toLowerCase(); });
    var key = parts.pop();
    var needCtrl = parts.indexOf('ctrl') >= 0, needShift = parts.indexOf('shift') >= 0, needAlt = parts.indexOf('alt') >= 0;
    if (!!ev.ctrlKey !== needCtrl || !!ev.shiftKey !== needShift || !!ev.altKey !== needAlt) return false;
    var k = (ev.key || '').toLowerCase();
    if (key === 'space') return k === ' ' || k === 'spacebar' || ev.code === 'Space';
    return k === key;
  }
  document.addEventListener('keydown', function (ev) {
    if (ev.repeat) return;
    if (cfg.mode !== 'local') return;   // hotkey only drives local mode
    if (hotkeyMatches(ev, cfg.hotkey)) { ev.preventDefault(); ev.stopPropagation(); onLocalToggle(); }
  }, true);

  // ---- skins ----
  function ensureCanvas() {
    if (canvas) return;
    var composer = findComposer();
    if (!composer) return;
    var host = composer.parentElement || composer;
    canvas = mk('canvas', { id: 'zvoice-canvas' },
      'position:absolute;inset:0;width:100%;height:100%;pointer-events:none;display:none;z-index:0;');
    var hs = window.getComputedStyle(host);
    if (hs.position === 'static') host.style.position = 'relative';
    host.appendChild(canvas);
    cctx = canvas.getContext('2d');
  }
  function resizeCanvas() {
    if (!canvas) return;
    var r = canvas.parentElement.getBoundingClientRect();
    var dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.floor(r.width * dpr));
    canvas.height = Math.max(1, Math.floor(r.height * dpr));
    if (cctx) cctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  function startSkin() {
    if (cfg.skin === 'default') { rafId = 0; return; }
    ensureCanvas();
    if (!canvas) return;
    canvas.style.display = 'block';
    resizeCanvas();
    var t = 0;
    var loop = function () {
      if (!analyser) return;
      analyser.getByteFrequencyData(freq);
      t += 0.05;
      if (cfg.skin === 'wave') drawWave(freq, t);
      else drawHalo(freq, t);
      rafId = requestAnimationFrame(loop);
    };
    rafId = requestAnimationFrame(loop);
  }
  function stopSkin() {
    if (rafId) { cancelAnimationFrame(rafId); rafId = 0; }
    if (canvas) { canvas.style.display = 'none'; if (cctx) cctx.clearRect(0, 0, canvas.width, canvas.height); }
  }
  function drawWave(data, t) {
    if (!cctx) return;
    var w = canvas.clientWidth, h = canvas.clientHeight;
    var bars = 64;
    cctx.clearRect(0, 0, w, h);
    var bw = w / bars;
    for (var i = 0; i < bars; i++) {
      var v = data[Math.floor(i * data.length / bars)] / 255;
      var bh = Math.max(1.5, v * h * 0.75);
      var g = cctx.createLinearGradient(0, h, 0, h - bh);
      g.addColorStop(0, 'rgba(34,211,238,0.42)');
      g.addColorStop(1, 'rgba(139,92,246,0.16)');
      cctx.fillStyle = g;
      var x = i * bw + bw * 0.18;
      cctx.fillRect(x, h - bh, bw * 0.64, bh);
      cctx.fillStyle = 'rgba(165,243,252,0.5)';
      cctx.fillRect(x, h - bh, bw * 0.64, 1.2);
    }
  }
  function drawHalo(data, t) {
    if (!cctx) return;
    var b = findOfficialBtn();
    if (!b) return;
    var cr = b.getBoundingClientRect();
    var pr = canvas.getBoundingClientRect();
    var cx = cr.left - pr.left + cr.width / 2;
    var cy = cr.top - pr.top + cr.height / 2;
    var w = canvas.clientWidth, h = canvas.clientHeight;
    cctx.clearRect(0, 0, w, h);
    var base = 26;
    cctx.beginPath();
    for (var a = 0; a <= 128; a++) {
      var ang = (a / 128) * Math.PI * 2 - Math.PI / 2;
      var v = data[a % data.length] / 255;
      var r = base + v * 16 + Math.sin(t + a * 0.15) * 1.2;
      var x = cx + Math.cos(ang) * r, y = cy + Math.sin(ang) * r;
      if (a === 0) cctx.moveTo(x, y); else cctx.lineTo(x, y);
    }
    cctx.closePath();
    cctx.strokeStyle = 'rgba(34,211,238,0.75)';
    cctx.lineWidth = 1.4;
    cctx.shadowColor = 'rgba(34,211,238,0.55)';
    cctx.shadowBlur = 8;
    cctx.stroke();
    cctx.shadowBlur = 0;
    cctx.beginPath();
    var r2 = base + 22;
    cctx.arc(cx, cy, r2, t * 1.4, t * 1.4 + Math.PI * 0.7);
    cctx.strokeStyle = 'rgba(139,92,246,0.55)';
    cctx.lineWidth = 1.2;
    cctx.stroke();
    cctx.beginPath();
    cctx.arc(cx, cy, r2 + 6, 0, Math.PI * 2);
    cctx.strokeStyle = 'rgba(255,255,255,0.08)';
    cctx.lineWidth = 1;
    cctx.stroke();
  }

  // ---- settings menu ----
  function closeMenu() {
    if (menu) { menu.remove(); menu = null; }
    document.removeEventListener('mousedown', onDocDown, true);
    document.removeEventListener('keydown', onMenuEsc, true);
  }
  function onDocDown(e) { if (menu && !menu.contains(e.target)) closeMenu(); }
  function onMenuEsc(e) { if (e.key === 'Escape') closeMenu(); }

  function openMenu() {
    if (menu) { closeMenu(); return; }
    loadConfig().then(function () {
      menu = mk('div', { id: 'zvoice-menu' },
        'position:fixed;z-index:2147483100;min-width:250px;padding:6px;border-radius:10px;'
        + 'background:rgba(24,24,32,.97);color:#ddd;font-size:12px;box-shadow:0 8px 30px rgba(0,0,0,.5);'
        + 'border:1px solid rgba(255,255,255,.08);backdrop-filter:blur(10px);font-family:system-ui,sans-serif;');
      var b = findOfficialBtn();
      var r = b ? b.getBoundingClientRect() : { left: 200, top: 400 };
      menu.style.left = Math.min(r.left, window.innerWidth - 270) + 'px';
      menu.style.bottom = (window.innerHeight - r.top + 6) + 'px';

      var title = mk('div', null, 'padding:4px 8px 6px;font-weight:600;color:#fff;');
      title.textContent = '语音输入设置';
      menu.appendChild(title);
      menu.appendChild(mk('div', null, 'height:1px;background:rgba(255,255,255,.08);margin:2px 0 6px;'));

      // ---- mode switch (the headline control) ----
      var modeRow = mk('div', null, 'padding:4px 8px 8px;');
      var modeLab = mk('div', null, 'color:#9aa;margin-bottom:5px;');
      modeLab.textContent = '识别模式';
      modeRow.appendChild(modeLab);
      var seg = mk('div', null, 'display:flex;gap:4px;');
      [['official', '官方云端'], ['local', '本地离线']].forEach(function (m) {
        var on = cfg.mode === m[0];
        var btn = mk('button', { type: 'button' },
          'flex:1;padding:6px 8px;border-radius:6px;cursor:pointer;font-size:11px;border:1px solid '
          + (on ? 'rgba(34,211,238,.6)' : 'rgba(255,255,255,.12)') + ';'
          + 'background:' + (on ? 'rgba(34,211,238,.16)' : 'transparent') + ';'
          + 'color:' + (on ? '#67e8f9' : '#bbb') + ';');
        btn.textContent = m[1];
        btn.addEventListener('click', function () {
          saveConfig({ mode: m[0] }).then(function () {
            notify(m[0] === 'local' ? '已切换：本地离线识别（音频不出本机）' : '已切换：官方云端识别');
            closeMenu();
          });
        });
        seg.appendChild(btn);
      });
      modeRow.appendChild(seg);
      var hint = mk('div', null, 'color:#667;margin-top:5px;line-height:1.4;font-size:10.5px;');
      hint.textContent = cfg.mode === 'local'
        ? '本地模式：SenseVoice 在本机运行，音频不上传。支持皮肤/热键/实时上字。'
        : '官方模式：走 ZCode 云端识别，需登录账号。右键可随时切到本地。';
      modeRow.appendChild(hint);
      menu.appendChild(modeRow);
      menu.appendChild(mk('div', null, 'height:1px;background:rgba(255,255,255,.08);margin:2px 0 6px;'));

      // ---- local-mode-only settings ----
      var localOnly = mk('div', null, cfg.mode === 'local' ? '' : 'opacity:.45;pointer-events:none;');
      localOnly.appendChild(rowToggle('随 ZCode 自动启动服务', cfg.autoStart, function (on) {
        saveConfig({ autoStart: on }).then(function () {
          notify('已' + (on ? '开启' : '关闭') + '自动启动（下次启动 ZCode 生效）');
        });
      }));
      localOnly.appendChild(rowSelect('输入设备', '<option value="">系统默认</option>', cfg.device, enumerateMics, function (v) {
        saveConfig({ device: v }).then(function () { notify('输入设备已切换（下次录音生效）'); });
      }));
      localOnly.appendChild(rowSelect('录音动效', [
        ['default', '默认电平条'], ['wave', '输入框声波'], ['halo', '麦克风声纹环'],
      ].map(function (x) { return '<option value="' + x[0] + '">' + x[1] + '</option>'; }).join(''), cfg.skin, null, function (v) {
        saveConfig({ skin: v }).then(function () { notify('皮肤已切换：' + ({ default: '电平条', wave: '声波', halo: '声纹环' }[v] || v)); });
      }));
      localOnly.appendChild(rowSelect('触发热键', ['Ctrl+Shift+Space', 'Alt+Q', 'Alt+V', 'Ctrl+Alt+Space']
        .map(function (k) { return '<option value="' + k + '">' + k + '</option>'; }).join(''),
        cfg.hotkey, null, function (v) { saveConfig({ hotkey: v }).then(function () { notify('热键已设为 ' + v); }); }));
      localOnly.appendChild(rowSelect('空闲自动退出', [[5, '5 分钟'], [10, '10 分钟'], [30, '30 分钟']]
        .map(function (x) { return '<option value="' + x[0] + '">' + x[1] + '</option>'; }).join(''),
        String(cfg.idleMin), null, function (v) { saveConfig({ idleMin: parseInt(v, 10) }).then(function () { notify('空闲退出已更新'); }); }));
      menu.appendChild(localOnly);

      menu.appendChild(mk('div', null, 'height:1px;background:rgba(255,255,255,.08);margin:6px 0;'));

      var stat = mk('div', null, 'padding:4px 8px;color:#9aa;line-height:1.5;');
      stat.textContent = '本地服务：检查中…';
      menu.appendChild(stat);
      manage('/status').then(function (s) {
        var deps = s.deps || {};
        stat.textContent = '本地服务：' + (s.sidecar === 'running' ? '运行中' : '未启动')
          + ' · 依赖：' + (deps.sherpaNode && deps.model ? '已就绪' : '待下载')
          + (s.error ? ' · ' + s.error : '');
      }).catch(function () { stat.textContent = '本地服务：管理器未响应'; });

      var actions = mk('div', null, 'display:flex;gap:6px;padding:4px 4px 2px;');
      var redl = mk('button', { type: 'button' },
        'flex:1;padding:5px 8px;border-radius:6px;border:1px solid rgba(255,255,255,.12);background:transparent;color:#ccc;cursor:pointer;font-size:11px;');
      redl.textContent = '检查/下载本地依赖';
      redl.addEventListener('click', function () {
        ensureOk = false;
        notify('正在检查本地依赖…');
        ensureService().then(function () { notify('依赖就绪，本地服务已启动'); closeMenu(); })
          .catch(function (e) { notify('失败：' + e.message); });
      });
      actions.appendChild(redl);
      menu.appendChild(actions);

      document.body.appendChild(menu);
      document.addEventListener('mousedown', onDocDown, true);
      document.addEventListener('keydown', onMenuEsc, true);
    });
  }

  function rowToggle(label, checked, onChange) {
    var row = mk('div', null, 'display:flex;align-items:center;justify-content:space-between;padding:5px 8px;border-radius:6px;cursor:pointer;');
    row.addEventListener('mouseenter', function () { row.style.background = 'rgba(255,255,255,.06)'; });
    row.addEventListener('mouseleave', function () { row.style.background = 'transparent'; });
    var lab = mk('span'); lab.textContent = label;
    var box = mk('input', { type: 'checkbox' }, 'accent-color:#22d3ee;cursor:pointer;');
    box.checked = !!checked;
    box.addEventListener('change', function () { onChange(box.checked); });
    row.appendChild(lab); row.appendChild(box);
    row.addEventListener('click', function (e) { if (e.target !== box) { box.checked = !box.checked; onChange(box.checked); } });
    return row;
  }

  function rowSelect(label, optionsHtml, value, asyncOptions, onChange) {
    var row = mk('div', null, 'display:flex;align-items:center;justify-content:space-between;gap:10px;padding:5px 8px;');
    var lab = mk('span', null, 'flex:0 0 auto;'); lab.textContent = label;
    var sel = mk('select', null, 'background:rgba(255,255,255,.06);color:#ddd;border:1px solid rgba(255,255,255,.12);border-radius:5px;font-size:11px;padding:3px 6px;max-width:130px;outline:none;');
    sel.innerHTML = optionsHtml;
    sel.value = value;
    sel.addEventListener('change', function () { onChange(sel.value); });
    row.appendChild(lab); row.appendChild(sel);
    if (asyncOptions) {
      asyncOptions().then(function (opts) {
        var cur = sel.value;
        sel.innerHTML = '<option value="">系统默认</option>' + opts.map(function (o) {
          return '<option value="' + o.id + '">' + (o.label || '麦克风 ' + o.id.slice(0, 8)) + '</option>';
        }).join('');
        sel.value = cur;
      }).catch(function () {});
    }
    return row;
  }

  function enumerateMics() {
    return navigator.mediaDevices.enumerateDevices().then(function (ds) {
      return ds.filter(function (d) { return d.kind === 'audioinput'; });
    });
  }

  function notify(text) {
    showBar('done', text);
    setTimeout(hideBar, 2500);
  }

  // ---- download progress via manager SSE ----
  var sse = null;
  function watchDownloads() {
    if (sse) return;
    resolveManager().then(function (port) {
      if (!port || sse) return;
      try {
        sse = new EventSource('http://127.0.0.1:' + port + '/events?t=' + encodeURIComponent(TOKEN));
        sse.addEventListener('progress', function (e) {
          var p = JSON.parse(e.data);
          showBar('wait', '下载 ' + p.item + ' ' + p.pct + '%', { progress: p.pct });
        });
      } catch (e) { /* optional */ }
    });
  }

  // ---- boot ----
  loadConfig().then(function () { watchDownloads(); });
  var tries = 0;
  function bootTick() {
    var b = findOfficialBtn();
    if (b && b !== officialBtn) {
      officialBtn = b;
      // Mark the button so the user can tell local mode is armed.
      if (cfg.mode === 'local') b.setAttribute('data-zvoice-mode', 'local');
      else b.removeAttribute('data-zvoice-mode');
    }
    if (++tries < 1200) setTimeout(bootTick, 1000);
    else setTimeout(bootTick, 5000);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bootTick);
  else bootTick();
})();

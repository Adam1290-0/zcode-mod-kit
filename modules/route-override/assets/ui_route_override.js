// ZCode route override — settings-page UI.
// Injects a "请求头 / 网络" row pair into the model-provider detail panel,
// next to the Base URL field. Anchors by structure (input[value^=http] ->
// field container), not by class names, so ZCode updates rarely break it.
// Talks to the wrapper's config server on 127.0.0.1:27891 (GET/POST /api/config).
// Re-asserted every 1.5s via interval (React re-renders may wipe the row).
(function () {
  'use strict';
  if (window.__zcodeRouteOverrideUI) return;
  window.__zcodeRouteOverrideUI = true;

  var API = 'http://127.0.0.1:27891';
  var TOKEN = (typeof ZRO_TOKEN === 'string') ? ZRO_TOKEN : ''; // injected at patch time
  var PROXY_DEFAULT = 'http://127.0.0.1:12334';
  var PRESETS = [
    { v: 'none', label: '默认（ZCode 原生）' },
    { v: 'claude-code', label: 'Claude Code' },
    { v: 'codex', label: 'Codex CLI' },
    { v: 'opensquilla', label: 'OpenSquilla' },
    { v: 'custom', label: '自定义…' },
  ];
  var NET_OPTS = [
    { v: 'direct', label: '直连' },
    { v: 'proxy', label: '走代理（VPN）' },
  ];
  var MY_ROW_ID = 'zro-row';
  var state = { routes: [], host: null };
  var loaded = false; // set after the first /api/config fetch resolves; blocks rendering "默认" from an empty state
  // ------------------------------------------------------------- config I/O
  function api(path, opts) {
    opts = opts || {};
    opts.headers = Object.assign({}, opts.headers, { 'x-zro-token': TOKEN });
    return fetch(API + path, opts).then(function (r) {
      if (!r.ok) throw new Error('config server ' + r.status);
      return r.json();
    });
  }
  function loadRoutes() {
    return api('/api/config').then(function (cfg) {
      state.routes = (cfg && cfg.routes) || [];
    }).catch(function () { state.routes = []; });
  }
  function saveRoutes(route, remove) {
    // Upsert: the server merges against ITS OWN disk state, so a stale UI
    // state can never wipe other providers' routes (vanishing-routes bug).
    return api('/api/config', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ mode: 'upsert', route: route, remove: !!remove }),
    }).then(function (r) {
      // refresh local mirror from server truth
      return loadRoutes().then(function () { return r; });
    });
  }

  // ------------------------------------------------------------- helpers
  function hostOf(url) {
    try { return new URL(url).hostname; } catch (e) { return null; }
  }
  function findRoute(host) {
    for (var i = 0; i < state.routes.length; i++) {
      if (state.routes[i].match === host) return state.routes[i];
    }
    return null;
  }
  function isCustom(route) {
    return route && route.preset === 'custom';
  }

  // ------------------------------------------------------------- DOM
  function isVisible(el) {
    if (!el || el.nodeType !== 1) return false;
    var cs = window.getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return false;
    if (cs.opacity === '0') return false;
    var r = el.getBoundingClientRect();
    // An invisible (display:none / detached) element reports 0x0 AND a null
    // offsetParent; a live panel can briefly report 0x0 while mounting, so
    // reject on the combination only, never on 0x0 alone.
    if (r.width === 0 && r.height === 0 && el.offsetParent === null) return false;
    return true;
  }
  // The EDIT panel is the one whose Base URL input is actually on screen.
  // Anchoring to the first VISIBLE URL input is the ground truth for "which
  // provider is being edited right now". The old "first password input"
  // heuristic broke for providers whose API key is not a password field
  // (openai / openai-compatible): it grabbed a different provider's password
  // box, resolved the wrong host, and the header dropdown showed "默认".
  // Walks up from an input to the first ancestor containing >=2 inputs (the
  // form-ish panel). Returns null when no such panel exists within 10 levels.
  function panelFromInput(inp) {
    var el = inp.parentElement;
    for (var up = 0; up < 10 && el && el !== document.body; up++) {
      if (el.querySelectorAll('input').length >= 2) return el;
      el = el.parentElement;
    }
    return null;
  }
  // A panel is "live" when the focused element or :focus-within sits inside
  // it; stale copies of the panel in hidden tabs fail this test.
  function isLivePanel(panel, activeEl) {
    if (activeEl && activeEl.nodeType === 1 && panel.contains(activeEl)) return true;
    if (!panel.matches) return false;
    try { return panel.matches(':focus-within'); } catch (e) { return false; }
  }
  var retryTimer = null;
  function schedulePanelRetry() {
    if (retryTimer) return; // at most one outstanding retry
    retryTimer = setTimeout(function () {
      retryTimer = null;
      try { mount(); } catch (e) { /* never break the host page */ }
    }, 150);
  }
  function findEditPanel() {
    var ae = document.activeElement;
    // The focused input is the strongest signal of which panel is being
    // edited right now; it beats any stale "first visible URL input" seated
    // in a dead tab or list item.
    if (ae && ae.nodeType === 1 && ae.tagName === 'INPUT') {
      var focusedUrl = /^https?:\/\//i.test(ae.value || '') ||
                       /example\.com/i.test(ae.placeholder || '');
      if (focusedUrl || ae.type === 'password') {
        var fromActive = panelFromInput(ae);
        if (fromActive) return fromActive;
      }
    }
    var all = document.querySelectorAll('input:not([type="password"])');
    var firstPanel = null;
    for (var i = 0; i < all.length; i++) {
      var v = all[i].value || '';
      var ph = all[i].placeholder || '';
      if (!/^https?:\/\//i.test(v) && !/example\.com/i.test(ph)) continue;
      if (!isVisible(all[i])) continue;
      var panel = panelFromInput(all[i]);
      if (!panel) continue; // no verified panel ancestor — skip this candidate
      if (isLivePanel(panel, ae)) return panel; // live panel wins outright
      if (!firstPanel) firstPanel = panel; // structural match, last-resort
    }
    // Nothing is focused yet (fresh edit-session): the first structural panel
    // is still the right guess — the old code returned an unverified shallow
    // parent here instead.
    if (firstPanel) return firstPanel;
    // Fallback: keep the password heuristic for panels not yet showing a URL.
    var pw = document.querySelector('input[type="password"]');
    if (pw) {
      var el = pw.parentElement;
      for (var up = 0; up < 10 && el && el !== document.body; up++) {
        var inputs = el.querySelectorAll('input:not([type="password"])');
        for (var j = 0; j < inputs.length; j++) {
          var v2 = inputs[j].value || '';
          var ph2 = inputs[j].placeholder || '';
          if (/^https?:\/\//i.test(v2) || /example\.com/i.test(ph2)) return el;
        }
        el = el.parentElement;
      }
      // A password exists but no panel resolved: the URL input is probably
      // still mounting, so retry shortly after.
      schedulePanelRetry();
    }
    return null;
  }
  function findBaseUrlInput(panel) {
    if (!panel) return null;
    var inputs = panel.querySelectorAll('input:not([type="password"])');
    for (var i = 0; i < inputs.length; i++) {
      var v = inputs[i].value || '';
      var ph = inputs[i].placeholder || '';
      if (/^https?:\/\//i.test(v) || /example\.com/i.test(ph)) return inputs[i];
    }
    return null;
  }
  function findFieldHost(panel) { // labeled field block wrapping the Base URL input
    var inp = findBaseUrlInput(panel);
    if (!inp) return null;
    var el = inp.parentElement;
    for (var up = 0; up < 4 && el; up++) {
      var labels = el.querySelectorAll('label, [class*="label"]');
      for (var i = 0; i < labels.length; i++) {
        if (/base\s*url/i.test(labels[i].textContent || '')) return el;
      }
      el = el.parentElement;
    }
    return inp.parentElement;
  }

  function makeSelect(id, options, value, onChange) {
    var sel = document.createElement('select');
    sel.id = id;
    sel.style.cssText = 'width:100%;height:32px;padding:0 8px;font-size:13px;color:inherit;'
      + 'background:var(--background,#1b1d1f);border:1px solid var(--border,rgba(255,255,255,.12));'
      + 'border-radius:6px;outline:none;cursor:pointer;';
    options.forEach(function (o) {
      var op = document.createElement('option');
      op.value = o.v; op.textContent = o.label;
      sel.appendChild(op);
    });
    sel.value = value;
    sel.addEventListener('change', function () { onChange(sel.value); });
    return sel;
  }
  function makeLabel(text) {
    var lb = document.createElement('label');
    lb.textContent = text;
    lb.style.cssText = 'display:block;margin-bottom:4px;font-size:13px;'
      + 'color:var(--foreground-subtle,#9a9ea3);';
    return lb;
  }
  function makeTextarea(text, onChange) {
    var ta = document.createElement('textarea');
    ta.rows = 3;
    ta.placeholder = 'Header-Name: Value  （每行一条，-Header-Name 表示删除）';
    ta.value = text;
    ta.style.cssText = 'width:100%;margin-top:6px;padding:6px 8px;font-size:12px;'
      + 'font-family:Consolas,monospace;color:inherit;'
      + 'background:var(--background,#1b1d1f);border:1px solid var(--border,rgba(255,255,255,.12));'
      + 'border-radius:6px;outline:none;resize:vertical;';
    var t;
    ta.addEventListener('input', function () {
      clearTimeout(t);
      t = setTimeout(function () { onChange(ta.value); }, 600);
    });
    return ta;
  }
  function makeProxyInput(value, onChange) {
    var inp = document.createElement('input');
    inp.type = 'text';
    inp.value = value;
    inp.placeholder = 'http://127.0.0.1:12334';
    inp.style.cssText = 'width:100%;margin-top:6px;padding:6px 8px;font-size:12px;'
      + 'font-family:Consolas,monospace;color:inherit;'
      + 'background:var(--background,#1b1d1f);border:1px solid var(--border,rgba(255,255,255,.12));'
      + 'border-radius:6px;outline:none;';
    var t;
    inp.addEventListener('input', function () {
      clearTimeout(t);
      t = setTimeout(function () { onChange(inp.value.trim()); }, 600);
    });
    return inp;
  }
  function badge(text, ok) {
    var b = document.createElement('span');
    b.textContent = text;
    b.style.cssText = 'margin-left:8px;font-size:11px;color:' +
      (ok ? '#6ee7b7' : '#f87171') + ';';
    return b;
  }

  function applyPreset(route, preset) { // preset select changed
    if (preset === 'custom') {
      route.preset = 'custom';
      route.customHeaders = route.customHeaders || {};
    } else {
      route.preset = preset;
      delete route.customHeaders;
    }
  }

  function ensureRoute(host) {
    var r = findRoute(host);
    if (!r) {
      r = { match: host, preset: 'none', proxy: null };
      state.routes.push(r);
    }
    return r;
  }
  function dropRoute(host) {
    state.routes = state.routes.filter(function (r) { return r.match !== host; });
  }

  function buildRow(host) {
    var route = findRoute(host);
    var presetV = route ? (isCustom(route) ? 'custom' : (route.preset || 'none')) : 'none';
    var netV = (route && route.proxy) ? 'proxy' : 'direct';
    var saveTimer = null;

    var row = document.createElement('div');
    row.id = MY_ROW_ID;
    row.style.cssText = 'display:flex;gap:12px;margin-top:10px;flex-wrap:wrap;';

    var colA = document.createElement('div');
    colA.style.cssText = 'flex:1 1 220px;min-width:200px;';
    var colB = document.createElement('div');
    colB.style.cssText = 'flex:1 1 220px;min-width:200px;';

    var statusA = badge('', true);

    colA.appendChild(makeLabel('请求头'));
    colA.appendChild(makeSelect('zro-preset', PRESETS, presetV, function (v) {
      var r = ensureRoute(host);
      applyPreset(r, v);
      if (r.preset === 'none' && !r.proxy) dropRoute(host); // fully default -> remove route
      scheduleSave();
      rerender();
    }));

    var colBWrap = colB;
    colB.appendChild(makeLabel('网络'));
    colB.appendChild(makeSelect('zro-net', NET_OPTS, netV, function (v) {
      var r = ensureRoute(host);
      r.proxy = (v === 'proxy') ? (r.proxy || PROXY_DEFAULT) : null;
      if (r.preset === 'none' && !r.proxy) dropRoute(host);
      scheduleSave();
      rerender();
    }));

    // custom headers textarea + proxy url input live in an extra full-width row
    var extra = document.createElement('div');
    extra.style.cssText = 'width:100%;';

    function rerender() {
      var cur = findRoute(host);
      var showCustom = cur && isCustom(cur);
      var showProxy = cur && cur.proxy;
      extra.textContent = '';
      if (showCustom) {
        var lines = [];
        var ch = (cur && cur.customHeaders) || {};
        Object.keys(ch).forEach(function (k) { lines.push(k + ': ' + ch[k]); });
        (cur.removeHeaders || []).forEach(function (k) { lines.push('-' + k); });
        extra.appendChild(makeTextarea(lines.join('\n'), function (text) {
          var r = ensureRoute(host);
          var headers = {}, removes = [];
          text.split('\n').forEach(function (line) {
            line = line.trim();
            if (!line) return;
            if (line[0] === '-') { removes.push(line.slice(1).trim()); return; }
            var ix = line.indexOf(':');
            if (ix > 0) headers[line.slice(0, ix).trim()] = line.slice(ix + 1).trim();
          });
          r.customHeaders = headers;
          r.removeHeaders = removes;
          scheduleSave();
        }));
      }
      if (showProxy) {
        extra.appendChild(makeProxyInput(cur.proxy, function (val) {
          var r = ensureRoute(host);
          r.proxy = val || PROXY_DEFAULT;
          scheduleSave();
        }));
      }
    }

    function scheduleSave() {
      statusA.textContent = '保存中…';
      clearTimeout(saveTimer);
      saveTimer = setTimeout(function () {
        // upsert THIS provider's route only; server merges against disk truth
        var r = findRoute(host);
        saveRoutes(r, !r).then(function () {
          statusA.textContent = '✓ 已生效';
          setTimeout(function () { statusA.textContent = ''; }, 1600);
        }).catch(function () {
          statusA.textContent = '✗ 保存失败';
        });
      }, 400);
    }

    rerender();
    row.appendChild(colA);
    row.appendChild(colB);
    row.appendChild(statusA);
    var holder = document.createElement('div');
    holder.style.cssText = 'width:100%;';
    holder.appendChild(row);
    holder.appendChild(extra);
    return holder;
  }

  // Resolves the provider currently shown in the EDIT panel, fresh every call.
  // Returns null when no provider panel is open (e.g. list-only view).
  function currentPanelHost() {
    var panel = findEditPanel();
    if (!panel) return null;
    var inp = findBaseUrlInput(panel);
    if (!inp) return null;
    return hostOf(inp.value || '');
  }

  function unmount() {
    var existing = document.getElementById(MY_ROW_ID);
    if (existing) {
      var holder = existing.closest('[data-zro-holder]') || existing;
      if (holder.parentElement) holder.parentElement.removeChild(holder);
    }
  }

  function mount(force) {
    var host = currentPanelHost();
    if (!host) { unmount(); currentHost = null; return; }
    if (!loaded) return; // first /api/config fetch still pending; the caller below force-mounts when it resolves

    var existing = document.getElementById(MY_ROW_ID);
    if (!force && existing && currentHost === host &&
        existing.closest('[data-zro-holder]') &&
        document.contains(existing)) return; // correct provider, still alive

    // provider switched (or first mount): rebuild from scratch so the row,
    // textarea and proxy input all reflect THIS provider's route only
    unmount();
    currentHost = host;

    var panel = findEditPanel();
    var hostEl = findFieldHost(panel);
    if (!hostEl) return;

    var ui = buildRow(host);
    ui.setAttribute('data-zro-holder', '1');
    ui.dataset.zroHost = host;
    hostEl.parentElement.insertBefore(ui, hostEl.nextSibling);
  }
  var currentHost = null;

  // Immediate refresh on provider switch. MutationObserver fires only when the
  // DOM actually changes (React rebuilds the provider panel on switch), so it
  // costs nothing while idle — unlike the old 1.5s poll. Our own injected row
  // (and its holder) is filtered out so the observer never loops on itself;
  // mount() is already idempotent as a second guard.
  var moTimer = null;
  function scheduleMountSoon() {
    if (moTimer) return;
    moTimer = setTimeout(function () {
      moTimer = null;
      try { mount(); } catch (e) { /* never break the host page */ }
    }, 50);
  }
  function isOurNode(node) {
    if (!node || node.nodeType !== 1) return false; // element nodes only
    if (node.id === MY_ROW_ID) return true;
    if (node.hasAttribute && node.hasAttribute('data-zro-holder')) return true;
    return !!(node.closest && node.closest('#' + MY_ROW_ID + ', [data-zro-holder]'));
  }
  var mo = new MutationObserver(function (muts) {
    for (var i = 0; i < muts.length; i++) {
      var m = muts[i];
      var onlyOurs = true;
      for (var j = 0; j < m.addedNodes.length; j++) {
        if (!isOurNode(m.addedNodes[j])) { onlyOurs = false; break; }
      }
      if (onlyOurs) {
        for (var k = 0; k < m.removedNodes.length; k++) {
          if (!isOurNode(m.removedNodes[k])) { onlyOurs = false; break; }
        }
      }
      if (!onlyOurs) { scheduleMountSoon(); return; }
    }
  });
  mo.observe(document.body, { childList: true, subtree: true });

  // Fallback poll (reduced): re-assert the row if React reconciliation removes
  // it without a provider switch (rare). Not the primary refresh path anymore.
  setInterval(function () {
    try { mount(); } catch (e) { /* never break the host page */ }
  }, 3000);
  loadRoutes().then(function () {
    loaded = true;
    try { mount(true); } catch (e) {}
  });

  // --------------------------------------------------------------- ad banner
  // Same sharellm.net banner as the account-switcher plugin shows on this page.
  // Runtime yield: if the account-switcher's ad (data-zca-ad-model) is present,
  // ours is removed — so the two plugins never show two banners at once,
  // regardless of injection order. Re-asserted on the same 3s poll.
  function openAdUrl() {
    var url = 'https://sharellm.net/sign-up?aff=wb5b';
    try {
      if (window.zcode && typeof window.zcode.openExternal === 'function') {
        window.zcode.openExternal(url);
        return;
      }
    } catch (e) {}
    try { window.open(url, '_blank'); } catch (e) {}
  }
  function ensureAdStyle() {
    if (document.getElementById('zro-ad-style')) return;
    var st = document.createElement('style');
    st.id = 'zro-ad-style';
    st.textContent = '.zro-model-ad{display:block;cursor:pointer;font-size:12.5px;font-weight:600;'
      + 'color:#e0edff;text-align:center;padding:8px 14px;border:1px solid rgba(147,197,253,.55);'
      + 'border-radius:8px;background:linear-gradient(90deg,rgba(37,99,235,.30),rgba(139,92,246,.30))}'
      + '.zro-model-ad:hover{background:linear-gradient(90deg,rgba(37,99,235,.45),rgba(139,92,246,.45));'
      + 'border-color:rgba(147,197,253,.9)}';
    (document.head || document.documentElement).appendChild(st);
  }
  function assertAdBanner() {
    try {
      var mine = document.querySelector('[data-zro-ad-model]');
      // account-switcher's banner wins — remove ours and stand down.
      if (document.querySelector('[data-zca-ad-model]')) {
        if (mine && mine.parentElement) mine.parentElement.removeChild(mine);
        return;
      }
      if (mine) return; // already ours, alive
      // Anchor: the model-settings description text (same as account-switcher).
      var best = null, bestLen = 1e9;
      var els = document.querySelectorAll('p,span,div,h1,h2,h3,h4');
      for (var i = 0; i < els.length; i++) {
        var t = (els[i].textContent || '').replace(/\s+/g, '');
        if (t.length < 200 &&
            (t.indexOf('管理自定义模型供应商') >= 0 || /Managecustommodelproviders/i.test(t))) {
          if (t.length < bestLen) { best = els[i]; bestLen = t.length; }
        }
      }
      if (!best) return;
      var headerRow = best.parentElement;
      if (!headerRow || !headerRow.parentNode) return;
      ensureAdStyle();
      var ad = document.createElement('div');
      ad.setAttribute('data-zro-ad-model', '1');
      ad.className = 'zro-model-ad';
      ad.textContent = '✨ AI 模型共享，尽在 sharellm.net';
      ad.title = '点击访问 sharellm.net';
      ad.addEventListener('click', function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        openAdUrl();
      });
      headerRow.parentNode.insertBefore(ad, headerRow.nextSibling);
    } catch (e) { /* never break the host page */ }
  }
  setInterval(assertAdBanner, 3000);
  assertAdBanner();
})();

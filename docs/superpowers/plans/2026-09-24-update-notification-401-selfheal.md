# Update Notification + 401 Self-Heal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the skin-panel update notification (per approved spec) and fix the reported `unauthorized` bug class (service booting with an empty/unreadable auth token rejects everything until restart).

**Architecture:** Two independent changes in one release. (1) Version notification: `modkit.py` owns `KIT_VERSION`, passes `--kit-version` to skin-manager's injector, which bakes it into `ui_skin.js`; the renderer checks GitHub Releases daily (day-stamped localStorage) and prepends a banner row in the panel when remote > local. (2) 401 self-heal: all three token-consuming runtimes (route wrapper, pin wrapper, account-switcher main) re-read their auth-token file on demand when it is missing/empty or a request arrives unmatched, instead of staying wedged with an empty token until process restart.

**Tech Stack:** Python stdlib (modkit, injectors, check()-based tests), Node/Electron renderer+main JS.

## Global Constraints

- Token baking: bare replacement only, never `repr()` around quotes (account-switcher v1.0.3 bug class); baked JS blocks must pass `node --check`.
- Byte-exact restore: writes that must round-trip asar files use `newline=""`.
- Renderer must never break the host app: every new fetch wrapped, all errors silent.
- GitHub API unauthenticated only; 8s AbortController timeout; once per calendar day max (`localStorage` stamp `zkit_last_check`).
- Existing suites must stay green: `tests/test_engine.py` (18), `tests/test_modules.py` (50), `tests/test_edge_cases.py` (52).
- Do not touch the running ZCode or run `install.bat` during development.
- Commit after each task; commit messages in English.

---

### Task 1: KIT_VERSION plumbing (modkit.py + skin inject.py)

**Files:**
- Modify: `modkit.py` (top constants area ~line 50, and `module_cmd()` ~line 442)
- Modify: `modules/skin-manager/inject.py`

**Interfaces:**
- Produces: `KIT_VERSION` constant in modkit.py; skin `inject.py` accepts `--kit-version <str>`; skin injector replaces `__ZCKIT_VERSION__` placeholder in `ui_skin.js` with `json.dumps(version)`.

- [ ] **Step 1: Write the failing test** (add to `tests/test_modules.py`)

```python
def test_kit_version_baking():
    # skin inject with --kit-version replaces the placeholder with a JSON string
    work = make_tree(work_root())
    env = env_for(work)
    rc, out = run(module("skin-manager") / "inject.py",
                  ["--dir", str(work), "--kit-version", "1.2.0"], env)
    check("skin: --kit-version inject exit 0", rc == 0, out[-200:])
    html = (work / "out" / "renderer" / "index.html").read_text(encoding="utf-8", newline="")
    check("skin: kit version baked", '"1.2.0"' in html and "__ZCKIT_VERSION__" not in html)
```

Also assert the no-flag path keeps the placeholder (existing tests cover plain inject — add one negative check).

- [ ] **Step 2: Run test to verify it fails**

Run: `python tests/test_modules.py`
Expected: FAIL — `--kit-version` is an unrecognized argument (argparse exits 2).

- [ ] **Step 3: Implement**

modkit.py — near `AD_URL`:

```python
KIT_VERSION = "1.2.0"
```

modkit.py — in `module_cmd()`, after existing arg assembly:

```python
    if "zcode-cjs" in mod.get("targets", []) or mod.get("slug") == "skin-manager":
        args += ["--kit-version", KIT_VERSION]
```

Note: pass `--kit-version` only to skin-manager (only consumer); simpler: check slug equality alone. Final code:

```python
    if mod.get("slug") == "skin-manager":
        args += ["--kit-version", KIT_VERSION]
```

skin inject.py — add argument and bake step (before renderer write):

```python
    ap.add_argument("--kit-version", default=None,
                    help="bake the mod-kit version into the ui script")
```

Where the js source is read:

```python
        js = read_raw(assets / "ui_skin.js")
        if "__ZCKIT_VERSION__" in js:
            kv = json.dumps(args.kit_version) if args.kit_version else '"__ZCKIT_VERSION__"'
            js = js.replace('"__ZCKIT_VERSION__"', kv).replace("__ZCKIT_VERSION__", kv.strip('"') if args.kit_version else "__ZCKIT_VERSION__")
```

Actual implementation must keep it simple: only when `--kit-version` is provided, replace the quoted placeholder literal `"__ZCKIT_VERSION__"` with `json.dumps(version)`. Without the flag, touch nothing.

- [ ] **Step 4: Run tests**

Run: `python tests/test_modules.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add modkit.py modules/skin-manager/inject.py tests/test_modules.py
git commit -m "feat: bake KIT_VERSION into skin ui script via --kit-version"
```

### Task 2: Update banner in ui_skin.js

**Files:**
- Modify: `modules/skin-manager/assets/ui_skin.js`

**Interfaces:**
- Consumes: `KIT_VERSION` placeholder (Task 1), existing panel builder `buildPanel(panel, c)` and external-open helper.
- Produces: module state `window.__zkitUpdate = {newer: bool, tag: str}` and a banner row prepended in the panel.

- [ ] **Step 1: Implement the check + banner**

Top of the IIFE:

```js
  var KIT_VERSION = "__ZCKIT_VERSION__";
  var KIT_REPO = "Adam1290-0/zcode-mod-kit";

  // daily (calendar-day) update check; silent on every failure
  (function () {
    if (KIT_VERSION.indexOf("__ZCKIT_VERSION__") >= 0) return; // not baked
    try {
      var TODAY = new Date().toISOString().slice(0, 10);
      if (localStorage.getItem("zkit_last_check") === TODAY) return;
      localStorage.setItem("zkit_last_check", TODAY);
      var ctrl = new AbortController();
      var timer = setTimeout(function () { ctrl.abort(); }, 8000);
      fetch("https://api.github.com/repos/" + KIT_REPO + "/releases/latest",
            { signal: ctrl.signal })
        .then(function (r) { clearTimeout(timer); return r.ok ? r.json() : null; })
        .then(function (d) {
          if (!d || !d.tag_name) return;
          var remote = d.tag_name.replace(/^v/, "");
          var mine = KIT_VERSION;
          var rn = remote.split("."), mn = mine.split(".");
          var newer = false;
          for (var i = 0; i < 3; i++) {
            var a = parseInt(rn[i] || "0", 10), b = parseInt(mn[i] || "0", 10);
            if (a > b) { newer = true; break; }
            if (a < b) break;
          }
          window.__zkitUpdate = { newer: newer, tag: remote };
        })
        .catch(function () {});
    } catch (e) {}
  })();
```

In `buildPanel(panel, c)`, before building the first row:

```js
    try {
      if (window.__zkitUpdate && window.__zkitUpdate.newer) {
        var up = document.createElement("div");
        up.style.cssText = "margin:2px 6px 8px;padding:8px 12px;border-radius:8px;cursor:pointer;" +
          "font-size:12.5px;font-weight:600;color:#fde68a;background:rgba(251,191,36,.12);" +
          "border:1px solid rgba(251,191,36,.45)";
        up.textContent = "\u26a0 Mod Kit v" + window.__zkitUpdate.tag +
          " available \u2014 click to open the release page";
        up.addEventListener("click", function (ev) {
          ev.preventDefault(); ev.stopPropagation();
          var url = "https://github.com/Adam1290-0/zcode-mod-kit/releases/latest";
          try { window.open(url, "_blank"); } catch (e) {}
        });
        panel.insertBefore(up, panel.firstChild);
      }
    } catch (e) {}
```

(If the panel builds rows imperatively rather than via innerHTML, insert the banner as the first child after the container is created — the implementer adapts to the actual builder signature.)

- [ ] **Step 2: Verify syntax**

Run: `node --check modules/skin-manager/assets/ui_skin.js`
Expected: no output (valid).

- [ ] **Step 3: Smoke-test version comparison**

```bash
node -e '
function isNewer(remote, mine){var r=remote.split("."),m=mine.split(".");
for(var i=0;i<3;i++){var a=parseInt(r[i]||"0",10),b=parseInt(m[i]||"0",10);
if(a>b)return true;if(a<b)return false;}return false;}
console.log(isNewer("1.2.0","1.1.1")===true?"PASS newer":"FAIL");
console.log(isNewer("1.1.1","1.2.0")===false?"PASS older":"FAIL");
console.log(isNewer("1.2.0","1.2.0")===false?"PASS equal":"FAIL");
console.log(isNewer("2.0.0","1.9.9")===true?"PASS major":"FAIL");'
```

Expected: four PASS lines.

- [ ] **Step 4: Run skin mock roundtrip**

Run: `python tests/test_modules.py`
Expected: all PASS (byte-exact uninject unaffected — the placeholder isn't in the marker logic).

- [ ] **Step 5: Commit**

```bash
git add modules/skin-manager/assets/ui_skin.js
git commit -m "feat: daily update check + banner in skin panel"
```

### Task 3: 401 self-heal in the three token consumers

**Files:**
- Modify: `modules/route-override/assets/wrapper.js` (token block ~lines 21-26, auth check ~line 304)
- Modify: `modules/pin/assets/pin-wrapper.js` (token block ~lines 23-30, auth check ~line 236)
- Modify: `modules/account-switcher/assets/zcode-account-switcher-main.mjs` (token read, `tokenOk`)

**Bug mechanism (confirmed 2026-09-24):** each runtime reads its auth-token file **once at boot**; a transient failure (file busy mid-write during a concurrent install, AV scan lock, slow disk) leaves `AUTH_TOKEN = ""`, and `tokenOk` then rejects **every** request with 401 — the UI shows unauthorized, the profile list looks empty (renderer never receives /api/state), saves fail. Nothing is lost on disk (verified: profiles.json retained all 4 accounts; route-overrides.json untouched). Restart heals it, which is why the user saw it recover after relaunching.

**Interfaces:**
- Produces: in each runtime, a `refreshToken()` function that re-reads the token file; called lazily on each 401-bound check (cheap: one small file read only when the token is empty or the incoming header mismatches — never on every request path unconditionally).

- [ ] **Step 1: Implement refreshToken in route wrapper**

Replace the boot-time block:

```js
let AUTH_TOKEN = "";
try {
  const tokenFile = process.env.ZRO_TOKEN_FILE || path.join(DIR, "auth-token");
  AUTH_TOKEN = fs.readFileSync(tokenFile, "utf8").trim();
} catch (_) { AUTH_TOKEN = ""; }
if (!AUTH_TOKEN) log("WARN: auth-token missing - config server rejects all requests until it exists");
```

with:

```js
const TOKEN_FILE = process.env.ZRO_TOKEN_FILE || path.join(DIR, "auth-token");
let AUTH_TOKEN = "";
try { AUTH_TOKEN = fs.readFileSync(TOKEN_FILE, "utf8").trim(); } catch (_) {}
if (!AUTH_TOKEN) log("WARN: auth-token unreadable at boot - will retry on demand");
// 401 self-heal: a transient boot-time read failure (concurrent install /
// AV lock) used to wedge the server at AUTH_TOKEN="" rejecting everything
// until restart. Re-read lazily only when needed.
function refreshToken() {
  try { AUTH_TOKEN = fs.readFileSync(TOKEN_FILE, "utf8").trim(); } catch (_) {}
  return AUTH_TOKEN;
}
```

Auth check at ~line 304:

```js
    if ((!AUTH_TOKEN || !tokenEqual(req.headers["x-zro-token"], AUTH_TOKEN)) &&
        (!refreshToken() || !tokenEqual(req.headers["x-zro-token"], AUTH_TOKEN))) {
      res.writeHead(401); return res.end("unauthorized");
    }
```

- [ ] **Step 2: Same pattern in pin wrapper** (env `ZPIN_TOKEN` respected first: `refreshToken()` returns `process.env.ZPIN_TOKEN` if set, else re-reads the file). Auth check mirrors Step 1 with `x-zpin-token`.

- [ ] **Step 3: Same pattern in account-switcher main.mjs.** It currently reads `TOKEN_FILE` at boot:

```js
const TOKEN_FILE = path.join(PROFILES_DIR, 'auth-token');
let AUTH_TOKEN = '';
try { AUTH_TOKEN = fs.readFileSync(TOKEN_FILE, 'utf8').trim(); } catch {}
function refreshToken() {
  try { AUTH_TOKEN = fs.readFileSync(TOKEN_FILE, 'utf8').trim(); } catch {}
  return AUTH_TOKEN;
}
```

and `tokenOk` gains the same second-chance semantics:

```js
function tokenOk(req) {
  const got = String(req.headers['x-zca-token'] || '');
  let a = Buffer.from(AUTH_TOKEN);
  let b = Buffer.from(got);
  if ((a.length !== b.length || a.length === 0)) {
    // second chance: re-read the token file (boot-time transient failure heal)
    if (!refreshToken()) return false;
    a = Buffer.from(AUTH_TOKEN);
    if (a.length !== b.length || a.length === 0) return false;
  }
  return crypto.timingSafeEqual(a, b);
}
```

- [ ] **Step 4: Syntax + behavior verification**

```bash
node --check modules/route-override/assets/wrapper.js
node --check modules/pin/assets/pin-wrapper.js
node --check modules/account-switcher/assets/zcode-account-switcher-main.mjs
```

Behavior check (node harness): copy the current real `auth-token` into a temp DIR, boot logic simulation — set AUTH_TOKEN="", call refreshToken() twice (first restores, second no-op), assert non-empty and equal to the file. Also assert a mismatched-length request still 401s (tokenOk equivalent returns false).

- [ ] **Step 5: Run full suites**

Run: `python tests/test_engine.py && python tests/test_modules.py && python tests/test_edge_cases.py`
Expected: 18 + 50 + 52 all PASS.

- [ ] **Step 6: Commit**

```bash
git add modules/route-override/assets/wrapper.js modules/pin/assets/pin-wrapper.js modules/account-switcher/assets/zcode-account-switcher-main.mjs
git commit -m "fix: 401 self-heal - re-read auth-token on demand instead of wedging empty until restart"
```

### Task 4: Release v1.2.0

**Files:**
- Modify: `README.md` (changelog + badge), `modkit.py` (KIT_VERSION if not already 1.2.0), `modules/skin-manager/module.json`, `modules/account-switcher/module.json`, `modules/route-override/module.json`, `modules/pin/module.json` (version bumps + one-line notes)

- [ ] **Step 1: Bump versions** — kit 1.2.0; skin-manager 2.2.0 (new feature), account-switcher/pin/route-override patch bump (self-heal fix).
- [ ] **Step 2: Full suites + portability spot-check** (`find_zcode_root` still resolves).
- [ ] **Step 3: README changelog v1.2.0 + badge.**
- [ ] **Step 4: User reinstalls via install.bat (user-driven), post-install verification of the packed asar + simulated-old-version banner check.**
- [ ] **Step 5: Commit, tag v1.2.0, push, create GitHub Release.**

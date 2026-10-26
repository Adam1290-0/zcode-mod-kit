# Upgrade Playbook — adapting the kit to a new ZCode version

ZCode is closed-source and auto-updates. Every update replaces `app.asar` and
`resources/glm/zcode.cjs`, which **wipes all patches** — that is expected.
This document describes how the kit is re-verified and re-adapted after each
update.

**Read this file before touching anything after a ZCode update.**

---

## 0. Facts first

1. Read the new version out of the existing asar:

   ```bash
   python -c "import modkit; print(modkit.read_asar_version(r'<path>/app.asar'))"
   ```

2. Extract the new `app.asar` **once** into a scratch reference tree. All
   experiments run on private copies of that tree — never on a live install.

3. Confirm the four injection targets still exist:

   | Target | Used by |
   |--------|---------|
   | `out/renderer/index.html` | skin-manager, account-switcher, route-override, pin |
   | `out/main/index.js` | account-switcher (import), usage-bar (append line) |
   | `out/host/index.js` | snapshot-kill (may legitimately be gone) |
   | `resources/glm/zcode.cjs` (loose file) | route-override, pin, edit-resend-model-fix, usage-stats-fallback, zombie-cleanup |

4. Once the round is green, add the version to `VERIFIED_VERSIONS` in
   `modkit.py`. The version gate blocks installs on unlisted versions **by
   design** — an unlisted version means "not yet checked", not "probably fine".

## 1. Engine checks

- Re-verify `read_asar_version` / `asar_is_clean` against the new asar: read
  one entry through the header parser and compare bytes with the extracted
  file.
- `asar_is_clean` must scan **every** file a module writes to. It currently
  covers `out/renderer/index.html`, `out/host/index.js`, `out/main/index.js`
  and every `out/renderer/assets/*.js` chunk (edit-resend injects into a
  content-hashed chunk, not into `index.html`). A marker hidden in a file the
  scan does not read makes a patched asar look clean, and refreshing `kitbak`
  then overwrites the clean baseline.

## 2. Per-module check

| Module | Injection target / marker | What to check on a new version |
|--------|---------------------------|--------------------------------|
| route-override (order 10) | `zcode.cjs` `/*zro*/` + renderer `zcode-route-override-ui` | `"use strict"` header; the guarded require line stays inside the first 500 bytes; `var ZRO_TOKEN="<hex64>"` prologue survives re-inject |
| pin (order 20) | `zcode.cjs` `/*zpin*/` + renderer `zcode-pin-ui` | six renderer anchors; `system`-field matching in cjs; token baked as `var TOKEN = '<hex64>'` |
| skin-manager (order 30) | renderer `zcode-skin-ui` | `</body>` injection point; `chat-composer-region`, `chat-composer-input-surface`, `animate-spin`, `data-*-indicator` anchors. UI elements the upstream removes (e.g. `data-idle-indicator` on 3.16.2+) must hide their control rather than offer a dead option |
| account-switcher (order 40) | `out/main/index.js` import + renderer `zcode-account-switcher` | menu item regex `^(断开连接\|连接使用\|退出登录\|登出\|Disconnect\|Connect\|Log ?out\|Sign ?out)$` (normalized, ≤16 chars); settings nav `aria-label="主要项"/"Sections"`; model-provider description text; token baked as `var TOKEN = '<hex64>'` |
| snapshot-kill (order 50) | `out/host/index.js` `zcode-snapshot-kill-switch` | count symbols `RepoSnapshotSidecarService`, `captureBeforePromptUnsafe`, `flushActiveUpload`, `RepoSnapshotUploadWorker`; if all zero the module degrades to `[NOT-NEEDED]` (exit 0) — that is correct behavior, not a failure |
| usage-bar (order 60) | `out/main/index.js` append line + `[zusage]` | `out/main/index.js` exists and its tail accepts an appended import; loader uses only stable Electron APIs |
| edit-resend-model-fix (order 65) | `zcode.cjs` `zcode-editresend-model-fix` + renderer `zcode-editresend-ui` | cjs anchor `modelSelection:n.intent.modelSelection,mode:n.intent.mode,planEnabled:n.intent.planEnabled,` inside the canonical-intent builder (exactly once); `retryTurn` schema anchor; renderer edit/retry callbacks + the draft `useRef` name (`Tr.current` on 3.16.3) |
| usage-stats-fallback (order 70) | `zcode.cjs` `zusage-fb-day` + `zusage-fb-merge` | anchors `let R=e.prepare(` and `return{totals:{` each exactly once inside the queryAppUsage aggregation function; the day-map variable and the `.all(i,a,n,o)` call shape must still exist |
| zombie-cleanup (order 75) | `zcode.cjs` `zcode-zombie-cleanup` (shutdown handler) | anchor `f(),n(<name>(_))` inside the shutdown handler. **The minified name changes on nearly every release** (eNi → z7i → TYi → RYi so far); check this module first |

UI text anchors may live in renderer chunk files (`out/renderer/assets/*.js`)
on chunk-split builds — grep the whole renderer output, not just
`index.html`.

## 3. Verification

Run, and paste real output in the report:

```bash
python tests/test_engine.py
python tests/test_modules.py
python tests/test_edge_cases.py
node --check modules/<slug>/assets/*.js
python modules/<slug>/verify.py --dir <private extract copy>   # exit 0 required
```

Plus a round-trip on a private copy of the **real** new tree, not a mock:

1. inject every module
2. `node --check` on `zcode.cjs`, `out/main/index.js` and any patched
   renderer chunk
3. uninject everything
4. confirm `zcode.cjs` is **byte-identical** to the pristine file and every
   marker is gone from the asar

Never pipe `verify.py` through `tail` — it eats the exit code.

**A passing verifier must cover every write target of its module.** The kit's
installer skips a module entirely when its verifier exits 0, so anything the
verifier does not look at (for example a wrapper deployed to
`~/.zcode/plugins/<slug>/`) silently stays at whatever version was there
before.

## 4. Finalize

- Add the version to `VERIFIED_VERSIONS`, run the full suite, update the
  README compatibility matrix and changelog.
- Bump `module.json` version for every module whose code changed, with a
  one-line note on what the adaptation was.
- Reinstall via `install.bat` (user-driven), then re-verify the packed asar.
- **Publishing (push / tag / release) requires explicit user sign-off after
  the user has verified the result.**

## 5. Standing technical rules

- **Token baking**: replace the placeholder with the **bare** token — never
  `repr()` it (a quoted placeholder becomes `''token''` = invalid JS and the
  whole script block dies silently). After baking, the block must pass
  `node --check`. `verify.py` must reject any block that fails this.
- **Byte-exact restore**: any file write that must round-trip an asar file
  uses `newline=""` (Windows text mode translates `\n` → `\r\n` otherwise).
- **No machine-specific paths** in injected code or module assets. Anything
  the patch needs at runtime ships as a module asset and is deployed to
  `~/.zcode/plugins/<slug>/` by the module's `inject.py`.
- **`.bat` files**: pure ASCII + CRLF only; escape `|` as `^|` inside `echo`.
  Dry-run any bat change by replacing the python call with a marker echo and
  running it via `cmd /c`.
- **Never** refresh `app.asar.kitbak` from an asar that carries any module
  marker — the backup must stay the clean pre-patch baseline.
- **Event listeners**: a retry loop that calls `server.listen(port, callback)`
  accumulates one `listening` listener per attempt. Bind a single permanent
  handler and retry without a callback.

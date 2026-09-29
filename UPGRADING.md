# Upgrade Playbook — adapting the kit to a new ZCode version

## CURRENT ROUND STATUS (2026-09-29, ZCode 3.14.4 — COMPLETED, all clear)

| Module | Window (sessionId) | Result | Method |
|--------|---------------------|--------|--------|
| snapshot-kill | sess_74cf412e | ✅ NOT-NEEDED (4 symbols = 0) | resume via session-dispatch |
| edit-resend | sess_c70acbe6 | ✅ no change (anchor 1 hit) | resume via session-dispatch |
| pin | sess_057a52bd | ✅ no change (all anchors, zero residue) | resume via session-dispatch |
| route-override | sess_39ba00ea (model creation failed → fallback new session) | ✅ no change | resume + --fallback |
| account-switcher | sess_186ebe95 | ✅ no change (v1.0.8 mechanisms intact) | resume via session-dispatch |
| skin-manager + usage-bar | sess_1842e23a | ✅ both no change | resume via session-dispatch |
| usage-stats (zcode.cjs backfill) | sess_e488e7d1 (context stuck → new session blocked) | ⚠️ zusage.py CLI OK, zcode.cjs call chain reshaped (kRn entry, Xkr impl) → manual re-patch needed outside mod-kit scope | integrator self-check |

### Round summary

ZCode 3.14.4 is essentially a **no-change release** for mod-kit. All seven
modules survive with their anchors intact. 0 files were changed across all
module windows.

The one outlier is the **zcode.cjs usage-stat backfill** — `getAppUsageStats`
was renamed in 3.14.4 (now `kRn` at offset ~14489395 calling `g.queryAppUsage`).
The zusage.py CLI fallback (`_message_range_usage`) is DB-compatible and works
fine. The backfill patch will need manual re-insertion into the new Xkr / cRn
chain; this is tracked outside the mod-kit module set.

### Reference

- Reference tree: `G:/工作/测试/asar_3.14.4_ref` (shared read-only for all windows)
- Round execution: integrator → 7 windows via session-dispatch `resume`

ZCode is closed-source and auto-updates. Every update replaces `app.asar` and
`resources/glm/zcode.cjs`, which **wipes all patches** — that is expected. This
document defines how the kit is re-verified and re-adapted after each update,
and who is allowed to write what.

**Read this file before touching anything after a ZCode update.**

---

## 1. Roles and write domains

| Role | Owns (write) | Everything else |
|------|--------------|-----------------|
| **Integrator** (one agent only) | `modkit.py`, `tests/`, `.gitignore`, `README.md`, this file, handoff docs | read-only |
| **Module owner** (one per module) | `modules/<slug>/` — nothing else | read-only |

Hard rules:

- Exactly **one writer per file**. Never edit a shared file (`modkit.py`,
  `tests/`, another module's directory) from a module window — send the change
  to the integrator instead.
- The reference extract tree (a full `asar extract` of the new version) is
  **read-only for everyone**. Do all inject/verify experiments on a private
  copy in your own scratch directory, never on the shared tree.
- Do **not** touch a running ZCode, do not run `install.bat`, do not
  commit/push. Reinstalling is the integrator's call after all modules report.

## 2. Workflow after a ZCode update

### Step 0 — facts (integrator)

1. Read the new version: `python -c "import modkit; print(modkit.read_asar_version(r'<asar>'))"`.
2. Extract the new `app.asar` once into a shared reference tree.
3. Confirm the four injection targets still exist:

   | Target | Used by |
   |--------|---------|
   | `out/renderer/index.html` | skin-manager, account-switcher, route-override, pin |
   | `out/main/index.js` | account-switcher (import), usage-bar (append line) |
   | `out/host/index.js` | snapshot-kill (may legitimately be gone) |
   | `resources/glm/zcode.cjs` (loose file) | route-override `/*zro*/`, pin `/*zpin*/`, edit-resend-model-fix `zcode-editresend-model-fix` |

4. Update this file with the new version number and any changed anchors, then
   hand each module owner the go-ahead to run Step 2 for their module.

### Step 1 — engine adaptation (integrator)

- Add the new version to `VERIFIED_VERSIONS` in `modkit.py` — the version gate
  blocks installs on unlisted versions by design.
- Re-verify `read_asar_version` / `asar_is_clean` against the new asar: read
  one entry through the header parser and compare bytes with the extracted
  file.

### Step 2 — per-module check (each owner, own module only)

| Module | Injection target / marker | What to check on a new version |
|--------|---------------------------|--------------------------------|
| route-override (order 10) | `zcode.cjs` `/*zro*/` + renderer `zcode-route-override-ui` | `"use strict"` header, lazy fetch, `x-session-id`, `chat/completions` anchors; `var ZRO_TOKEN="<hex64>"` prologue survives re-inject |
| pin (order 20) | `zcode.cjs` `/*zpin*/` + renderer `zcode-pin-ui` | six renderer anchors; `system`-field matching in cjs; token baked as `var TOKEN = '<hex64>'` |
| skin-manager (order 30) | renderer `zcode-skin-ui` | `</body>` injection point; `chat-composer-region`, `chat-composer-input-surface`, `animate-spin`, `data-*-indicator` anchors |
| account-switcher (order 40) | `out/main/index.js` import + renderer `zcode-account-switcher` | menu item regex `^(断开连接\|连接使用\|退出登录\|登出\|Disconnect\|Connect\|Log ?out\|Sign ?out)$` (normalized, ≤16 chars); settings nav `aria-label="主要项"/"Sections"`; model-provider description text; token baked as `var TOKEN = '<hex64>'` |
| snapshot-kill (order 50) | `out/host/index.js` `zcode-snapshot-kill-switch` | count symbols `RepoSnapshotSidecarService`, `captureBeforePromptUnsafe`, `flushActiveUpload`, `RepoSnapshotUploadWorker`; if all zero the module degrades to `[NOT-NEEDED]` (exit 0) — that is correct behavior, not a failure |
| usage-bar (order 60) | `out/main/index.js` append line + `[zusage]` | `out/main/index.js` exists and its tail accepts an appended import; loader uses only stable Electron APIs (`BrowserWindow`, `ipcMain`, `webContents`) |
| edit-resend-model-fix (order 65) | `zcode.cjs` `zcode-editresend-model-fix` (inside `SJo` re-run) | anchor `modelSelection:o.intent.modelSelection,mode:o.intent.mode,planEnabled:o.intent.planEnabled,` matches EXACTLY once; if the minified shape drifts, refuse (exit 2) and report the new text |
| usage-stats-fallback (order 70) | `zcode.cjs` `zusage-fb-day` + `zusage-fb-merge` (inside `Xkr`) | anchors `let R=e.prepare(` and `return{totals:{` each match EXACTLY once inside Xkr body |
| zombie-cleanup (order 75) | `zcode.cjs` `zcode-zombie-cleanup` (shutdown handler) | anchor `f(),n(eNi(_))` matches EXACTLY once |

UI text anchors may live in renderer chunk files
(`out/renderer/assets/*.js`) on chunk-split builds — grep the whole renderer
output, not just `index.html`.

### Step 3 — verification (everyone, on own module)

Run, and paste real output in the report:

```bash
python tests/test_engine.py          # integrator-owned suite
python tests/test_modules.py
python tests/test_edge_cases.py
node --check modules/<slug>/assets/*.js
python modules/<slug>/verify.py --dir <private extract copy>   # exit 0 required
```

Plus a mock round-trip on a private copy: inject → verify (exit 0) →
re-inject (`[SKIP]`) → uninject → byte-identical restore. Never pipe
`verify.py` through `tail` — it eats the exit code.

### Step 4 — finalize

- Integrator: add the version to `VERIFIED_VERSIONS`, run the full suite,
  update README compatibility matrix, summarize.
- Module owners with code changes: bump `module.json` version, note the
  adaptation in one line.
- Only after every module reports green: reinstall via `install.bat`
  (user-driven), then verify the packed asar.

## 3. Standing technical rules

- **Token baking**: replace the placeholder with the **bare** token — never
  `repr()` it (a quoted placeholder becomes `''token''` = invalid JS and the
  whole script block dies silently). After baking, the block must pass
  `node --check`. `verify.py` must reject any block that fails this.
- **Byte-exact restore**: any file write that must round-trip an asar file
  uses `newline=""` (Windows text mode translates `\n` → `\r\n` otherwise).
- **`.bat` files**: pure ASCII + CRLF only; escape `|` as `^|` inside `echo`.
  Dry-run any bat change by replacing the python call with a marker echo and
  running it via `cmd /c`.
- **Never** refresh `app.asar.kitbak` from an asar that carries any module
  marker — the backup must stay the clean pre-patch baseline.
- Amounts/prices and any external publishing need explicit user sign-off.

## 4. Handoff docs

- `handoffs/<slug>-handoff.md` — per-module design notes and history.
- This file — the update workflow every module window follows.
- Module owners read **their** handoff plus this file; the integrator reads all.

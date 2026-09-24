# Update Notification for ZCode Mod Kit

Date: 2026-09-24
Status: design approved by user

## Goal

When the installed mod-kit version is older than the latest GitHub Release,
show one banner row at the very top of the skin manager panel, above the first
row (the "启动皮肤" row). Clicking it opens the GitHub Releases page.

## Decisions (agreed)

- **Channel**: GitHub Releases API `latest` endpoint (read `tag_name` only),
  unauthenticated, from the renderer.
- **Timing**: fire-and-forget fetch when the skin script loads (i.e. when ZCode
  starts and the plugin loads), throttled to **once per calendar day** via a
  `localStorage` day stamp `zkit_last_check=YYYY-MM-DD`. Any failure is silent;
  retry happens on the next calendar day.
- **Local version source**: single constant `KIT_VERSION` in `modkit.py` — the
  machine-readable source of truth, bumped on every release together with the
  README badge and changelog. Baked into `ui_skin.js` at inject time by
  replacing the placeholder `__ZCKIT_VERSION__`. The standalone skin repo
  never knows kit versions.
- **Click action**: open `https://github.com/Adam1290-0/zcode-mod-kit/releases/latest`
  via the same external-open pattern account-switcher uses
  (`window.zcode.openExternal`, fallback `window.open`).
- **Show condition**: banner only when remote > local (3-part numeric
  comparison). Equal, unparseable or absent remote -> no banner.

## Components and flow

1. `modkit.py`
   - Add `KIT_VERSION = "1.1.1"` near the top (single source of truth; bumped
     on every release).
   - `module_cmd()` passes `--kit-version <KIT_VERSION>` when invoking the
     skin-manager module.
2. `modules/skin-manager/inject.py`
   - New optional `--kit-version` argument (contract-compatible: absent =
     placeholder left as-is, matching the skip path).
   - Before writing the renderer block, replace `__ZCKIT_VERSION__` in the
     `ui_skin.js` source with `json.dumps(version)` — a bare JSON string, never
     `repr()` (repr-around-quotes is the token-baking bug class).
3. `modules/skin-manager/assets/ui_skin.js`
   - `var KIT_VERSION = "__ZCKIT_VERSION__";` (placeholder until baked).
   - `var KIT_REPO = "Adam1290-0/zcode-mod-kit";`
   - On script load, fire-and-forget async check:
     - If the placeholder was never replaced (old block), stop.
     - Day-stamp guard via `localStorage`; if `zkit_last_check` is today, stop.
     - Write the stamp, then `fetch("https://api.github.com/repos/" + KIT_REPO
       + "/releases/latest")` with an AbortController timeout of 8s.
     - Parse `tag_name`, strip a leading `v`, compare 3 numeric parts.
     - On remote > local: keep module-level state `{newer: true, tag}`.
     - Any error: silent.
   - In `buildPanel(panel, c)`: if state says newer, prepend a banner row above
     the first row, text (bilingual-lean):
     `⚠ Mod Kit v<tag> available — click to open the release page`.
     Click handler opens the release URL.
   - The banner re-renders on every panel rebuild while state stays newer.
     After the user actually updates, the day stamp prevents a re-check the
     same day; the next day's check (or a fresh ZCode start on another day)
     clears the state. Post-update the baked version equals remote and no
     banner is ever produced again.
4. `verify.py` / `uninject.py`: unchanged (the block is inert JS and gets
   removed wholesale; the placeholder does not affect `node --check`).

## Error handling

- Fetch failure / timeout / rate limit / parse failure: silent, day stamp
  already written, retry next calendar day.
- Placeholder not baked (old block): no check, no banner.
- Malformed version strings: no banner.

## Testing

- Python (integrator suite):
  - skin mock inject with `--kit-version 1.1.1` -> block contains `"1.1.1"`
    and no placeholder.
  - without the flag -> placeholder survives; verify exit 0 both ways;
    byte-exact uninject roundtrip unaffected.
  - Full suite green (120 existing checks + new ones).
- JS: `node --check` on `ui_skin.js`; version-compare logic smoke-tested with a
  small node harness that replicates the pure comparison function.
- Real machine: user visually confirms the banner row sits above the first
  panel row; simulate "remote newer" by baking an artificially old version in
  a scratch extract during development.

## Non-goals (YAGNI)

- No auto-download / auto-update.
- No new local service, no main-process changes.
- No popup/modal, no badge outside the skin panel.
- No configuration toggle for the check.
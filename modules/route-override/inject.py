#!/usr/bin/env python3
"""route-override module — directory-mode injector.

Usage:
  python inject.py --dir <extracted_asar_dir> [--zcode-cjs <path>] [--install-root <ZCode root>]

What it does (idempotent, marker-based):
  1. zcode.cjs file-level injection: one require() line after the first
     "use strict"; (marker /*zro*/, must sit within the first 500 bytes).
  2. asar renderer injection: <script id="zcode-route-override-ui"> block
     into out/renderer/index.html before </body>, with a generated auth token
     prologue (var ZRO_TOKEN=...). The same token is written to
     assets/auth-token so wrapper.js (loaded from the module dir) can read it.

Notes:
  - route-overrides.json is a RUNTIME config file, never distributed or
    touched by this injector (users already have their own).
  - wrapper.js resolves its config via __dirname; the module's assets dir is
    the canonical runtime home, so the require line points there.
"""
import argparse
import json
import os
import re
import secrets
import shutil
import sys
from pathlib import Path

SLUG = "route-override"
PREFIX = "[route-override]"

REQUIRE_MARKER = b"/*zro*/"
USE_STRICT = b'"use strict";'
RENDERER_MARKER = '<script id="zcode-route-override-ui">'
MAX_HEADER_BYTES = 500  # spec: injected line must sit within the first 500 bytes

# Persistent runtime home: wrapper.js, auth-token and route-overrides.json all
# live here so nothing depends on this module directory staying in place.
RUNTIME_DIR = Path(os.path.expanduser("~/.zcode/plugins/route-override"))


def log(msg: str) -> None:
    print(f"{PREFIX} {msg}")


def fail(msg: str) -> int:
    print(f"{PREFIX} [ERROR] {msg}")
    return 1


def read_raw(p: Path) -> bytes:
    return p.read_bytes()


def write_raw(p: Path, data) -> None:
    p.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))


# ---------------------------------------------------------------- zcode.cjs
def legacy_wrapper_dir(cjs_path: Path) -> Path | None:
    """Dir an existing /*zro*/ require line points to (pre-kit deployment)."""
    data = read_raw(cjs_path)
    idx = data.find(REQUIRE_MARKER)
    if idx < 0:
        return None
    start = data.rfind(b'try{require("', 0, idx)
    if start < 0 or idx - start > 400:
        return None
    uri = data[start + len(b'try{require("'):idx].decode("utf-8", "replace")
    p = Path(uri).parent
    return p if p.is_dir() else None


def deploy_runtime(wrapper_path: Path, cjs_path: Path | None) -> Path:
    """Copy wrapper.js into the persistent runtime dir. Migrate the user's
    existing route-overrides.json from a legacy deployment if present."""
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    dst = RUNTIME_DIR / "wrapper.js"
    shutil.copy2(wrapper_path, dst)
    cfg = RUNTIME_DIR / "route-overrides.json"
    if not cfg.exists() and cjs_path is not None:
        legacy = legacy_wrapper_dir(cjs_path)
        if legacy is not None:
            legacy_cfg = legacy / "route-overrides.json"
            if legacy_cfg.exists():
                shutil.copy2(legacy_cfg, cfg)
                log(f"migrated route-overrides.json from {legacy_cfg}")
    return dst


def inject_zcode_cjs(cjs_path: Path, wrapper_path: Path) -> bool:
    """Inject the one-line require. Returns True if injected, False if skipped."""
    wrapper_uri = str(wrapper_path.resolve().as_posix())
    require_line = b'try{require("' + wrapper_uri.encode() + b'")}catch(e){}/*zro*/'

    data = read_raw(cjs_path)
    if require_line in data:
        log(f"[SKIP] zcode.cjs already injected (safe form)")
        return False
    if REQUIRE_MARKER in data:
        # An older require line (different wrapper path) exists: replace it
        # instead of stacking a second one.
        m = data.find(REQUIRE_MARKER)
        ls = data.rfind(b"try{require(", 0, m)
        if ls < 0 or m - ls > 400:
            raise RuntimeError(
                "a /*zro*/ injection with unknown form exists in zcode.cjs; "
                "refusing to stack a second one (run uninject.py first)"
            )
        tail = m + len(REQUIRE_MARKER)
        if data[tail:tail + 2] == b"\r\n":
            tail += 2
        elif data[tail:tail + 1] == b"\n":
            tail += 1
        data = data[:ls] + data[tail:]
        log("replaced existing /*zro*/ require line (redeploy)")

    idx = data.find(USE_STRICT)
    if idx < 0 or idx > MAX_HEADER_BYTES:
        raise RuntimeError('"use strict"; anchor not found within the first 500 bytes of zcode.cjs')

    insert_at = idx + len(USE_STRICT)
    if insert_at + len(require_line) > MAX_HEADER_BYTES:
        # Anchor found but the line would end beyond the 500-byte window.
        raise RuntimeError(
            "injected line would end beyond the 500-byte header window "
            "(unusual zcode.cjs prologue); aborting"
        )
    write_raw(cjs_path, data[:insert_at] + require_line + data[insert_at:])
    log(f"injected require into zcode.cjs -> {wrapper_uri}")
    return True


def uninject_zcode_cjs(cjs_path: Path) -> bool:
    """Remove any /*zro*/ require line. Returns True if something was removed."""
    data = read_raw(cjs_path)
    idx = data.find(REQUIRE_MARKER)
    if idx < 0:
        log("zcode.cjs: no /*zro*/ marker, nothing to remove")
        return False
    # The line is: try{require("...")}catch(e){}/*zro*/  — find its start.
    start = data.rfind(b"try{require(", 0, idx)
    if start < 0 or idx - start > 400:
        raise RuntimeError("/*zro*/ marker found but its require line start could not be located")
    end = idx + len(REQUIRE_MARKER)
    write_raw(cjs_path, data[:start] + data[end:])
    log("removed require line from zcode.cjs")
    return True


# ---------------------------------------------------------------- renderer
def load_token(token_file: Path) -> str:
    if token_file.exists():
        t = token_file.read_text(encoding="utf-8").strip()
        if t:
            return t
    t = secrets.token_hex(32)
    token_file.write_text(t, encoding="utf-8")
    log(f"generated auth token -> {token_file}")
    return t

def inject_renderer(out_dir: Path, ui_js: Path, token: str) -> bool:
    html_path = out_dir / "out" / "renderer" / "index.html"
    if not html_path.exists():
        raise RuntimeError(f"renderer/index.html not found under {out_dir}")

    html = html_path.read_text(encoding="utf-8")
    js = ui_js.read_text(encoding="utf-8")
    # The token prologue MUST be part of EVERY block, fresh or replaced.
    # ui_route_override.js reads the global ZRO_TOKEN and the config server
    # rejects requests that lack it. The replace path (upgrading an older block)
    # used to drop the prologue, leaving the UI to send an empty token so every
    # call 401s until a full uninstall/reinstall (observed via reinstall.bat).
    prologue = "var ZRO_TOKEN=" + json.dumps(token) + ";\n"
    if RENDERER_MARKER in html:
        # Replace the whole previous block so the latest ui_route_override.js
        # (and a fresh token prologue) always wins (idempotent, no stale copies).
        end = html.find("</script>", html.find(RENDERER_MARKER))
        if end < 0:
            raise RuntimeError("renderer marker found but no closing </script>")
        tag = RENDERER_MARKER + "\n" + prologue + js + "\n</script>"
        html = html[: html.find(RENDERER_MARKER)] + tag + html[end + len("</script>"):]
        log("renderer script updated (replaced previous block)")
        write_raw(html_path, html)
        return True

    if "</body>" not in html:
        raise RuntimeError("</body> not found in renderer/index.html")
    tag = RENDERER_MARKER + "\n" + prologue + js + "\n</script>"
    html = html.replace("</body>", tag + "\n</body>", 1)
    write_raw(html_path, html)
    log("renderer script injected before </body>")
    return True


def uninject_renderer(out_dir: Path) -> bool:
    html_path = out_dir / "out" / "renderer" / "index.html"
    if not html_path.exists():
        raise RuntimeError(f"renderer/index.html not found under {out_dir}")
    html = html_path.read_text(encoding="utf-8")
    idx = html.find(RENDERER_MARKER)
    if idx < 0:
        log("renderer: no marker block, nothing to remove")
        return False
    end = html.find("</script>", idx)
    if end < 0:
        raise RuntimeError("renderer marker found but no closing </script>")
    # Also swallow the trailing newline we added after </script>.
    tail = end + len("</script>")
    if html[tail: tail + 1] == "\n":
        tail += 1
    html = html[:idx] + html[tail:]
    write_raw(html_path, html)
    log("removed renderer script block")
    return True


# ---------------------------------------------------------------- verify
def verify(out_dir: Path, cjs_path: Path | None) -> int:
    ok = True

    # zcode.cjs side: marker present, within first 500 bytes, exactly once.
    if cjs_path is None:
        log("verify: --zcode-cjs not given, skipping zcode.cjs checks")
        ok = False
    else:
        data = read_raw(cjs_path)
        first = data.find(REQUIRE_MARKER)
        count = data.count(REQUIRE_MARKER)
        if first < 0 or first + len(REQUIRE_MARKER) > MAX_HEADER_BYTES or count != 1:
            log(f"zcode.cjs: /*zro*/ marker missing/out-of-window/duplicated "
                f"(first={first}, count={count})")
            ok = False
        else:
            log("zcode.cjs: /*zro*/ marker OK (unique, within 500 bytes)")

    # renderer side: marker block exists and carries the current UI features.
    html_path = out_dir / "out" / "renderer" / "index.html"
    if not html_path.exists():
        log(f"renderer/index.html not found under {out_dir}")
        ok = False
    else:
        html = html_path.read_text(encoding="utf-8")
        idx = html.find(RENDERER_MARKER)
        if idx < 0:
            log("renderer: marker block missing")
            ok = False
        else:
            end = html.find("</script>", idx)
            block = html[idx:end] if end > idx else ""
            # Token must be the actual baked prologue assignment, not just the
            # identifier: ui_route_override.js references ZRO_TOKEN in its body,
            # so a bare '"ZRO_TOKEN" in block' check passed even when the prologue
            # (var ZRO_TOKEN="<hex>") was dropped on a block replace - the UI then
            # sent an empty token and every call 401d. Require the literal form.
            if not re.search(r'var ZRO_TOKEN="[0-9a-f]{64}"', block):
                log('renderer: baked token prologue missing (var ZRO_TOKEN="<hex>")')
                ok = False
            for feat in ("findEditPanel", "mode: 'upsert'",
                         "MutationObserver", "zro-model-ad", "assertAdBanner"):
                if feat not in block:
                    log(f"renderer: feature marker missing: {feat}")
                    ok = False
            if ok:
                log("renderer: UI block OK (baked token + findEditPanel + upsert "
                    "+ MutationObserver + ad banner)")

    if ok:
        log("verify: PASS")
        return 0
    log("verify: FAIL")
    return 1


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=f"{SLUG} directory-mode injector")
    ap.add_argument("--dir", required=True, help="extracted asar out directory")
    ap.add_argument("--zcode-cjs", default=None, help="path to resources/glm/zcode.cjs")
    ap.add_argument("--install-root", default=None, help="ZCode install root (unused; paths come from args)")
    args = ap.parse_args()

    out_dir = Path(args.dir)
    if not out_dir.exists():
        return fail(f"--dir not found: {out_dir}")
    module_root = Path(__file__).resolve().parent
    ui_js = module_root / "assets" / "ui_route_override.js"
    wrapper_js = module_root / "assets" / "wrapper.js"
    token_file = RUNTIME_DIR / "auth-token"
    if not ui_js.exists():
        return fail(f"missing asset: {ui_js}")
    if not wrapper_js.exists():
        return fail(f"missing asset: {wrapper_js}")

    try:
        cjs_path = Path(args.zcode_cjs) if args.zcode_cjs else None
        if cjs_path is not None:
            if not cjs_path.exists():
                return fail(f"--zcode-cjs not found: {cjs_path}")
            deployed = deploy_runtime(wrapper_js, cjs_path)
            inject_zcode_cjs(cjs_path, deployed)

        token = load_token(token_file)
        inject_renderer(out_dir, ui_js, token)
    except Exception as e:
        return fail(str(e))

    return verify(out_dir, Path(args.zcode_cjs) if args.zcode_cjs else None)


if __name__ == "__main__":
    sys.exit(main())

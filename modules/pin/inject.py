#!/usr/bin/env python3
"""pin module — directory-mode injector for the ZCode Mod Kit.

Targets:
- zcode-cjs: one try/catch require line in resources/glm/zcode.cjs (marker /*zpin*/).
  Anchor: route-override's /*zro*/ marker if present, else fall back to
  'use strict'; — pin must stay the OUTERMOST fetch patch either way.
- asar: renderer/index.html <script id="zcode-pin-ui"> block with the auth token
  baked in via the '__ZPIN_TOKEN__' placeholder (never a window global).

Usage:
  python inject.py --dir <extracted-asar-root> [--zcode-cjs <path>] [--install-root <root>]

Idempotent: prints [SKIP] and exits 0 when all markers are already present.
Standard library only. All output lines are prefixed with [pin].
"""
import sys, secrets, argparse, os, shutil
from pathlib import Path

WRAPPER_MARKER = b"/*zpin*/"
RO_ANCHOR = b"/*zro*/"
USE_STRICT_ANCHOR = b'"use strict";'
UI_MARKER = '<script id="zcode-pin-ui">'
TOKEN_PLACEHOLDER = "'__ZPIN_TOKEN__'"
DATA_DIR = Path(os.path.expanduser("~/.zcode/plugins/pin"))


def log(msg):
    print("[pin] " + msg)


def require_line_for(wrapper_path: Path) -> bytes:
    uri = str(wrapper_path.resolve().as_posix())
    return b'try{require("' + uri.encode() + b'")}catch(e){}' + WRAPPER_MARKER


def deploy_wrapper(wrapper_js: Path) -> Path:
    """Deploy the wrapper AND its same-directory dependency (pin-core.js,
    required at wrapper top via require(path.join(__dirname,...))) to the
    persistent runtime dir, so zcode.cjs never depends on this module
    directory staying in place. Missing the core kills the whole module with
    a silent MODULE_NOT_FOUND swallowed by the try/catch require line."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dst = DATA_DIR / wrapper_js.name
    shutil.copy2(wrapper_js, dst)
    for dep in ("pin-core.js",):
        dep_src = wrapper_js.parent / dep
        if dep_src.exists():
            shutil.copy2(dep_src, DATA_DIR / dep)
    log("deployed wrapper + deps -> " + str(DATA_DIR))
    return dst


def inject_zcode_cjs(zcjs: Path, wrapper_js: Path) -> bool:
    if not zcjs.exists():
        log("ERROR zcode.cjs not found: " + str(zcjs))
        return False
    data = zcjs.read_bytes()
    line = require_line_for(wrapper_js)
    if line in data:
        log("SKIP zcode.cjs already has pin require line")
        return True
    if WRAPPER_MARKER in data:
        # An older require line (different wrapper path) exists: replace it
        # instead of stacking a second one.
        m = data.find(WRAPPER_MARKER)
        ls = data.rfind(b"try{require(", 0, m)
        if ls < 0 or m - ls > 400:
            log("ERROR unknown /*zpin*/ injection exists; abort to avoid stacking")
            return False
        tail = m + len(WRAPPER_MARKER)
        if data[tail:tail + 2] == b"\r\n":
            tail += 2
        elif data[tail:tail + 1] == b"\n":
            tail += 1
        data = data[:ls] + data[tail:]
        log("replaced existing pin require line (redeploy)")
    idx = data.find(RO_ANCHOR)
    if 0 <= idx <= 500:
        insert_at = idx + len(RO_ANCHOR)
        log("anchoring after route-override marker")
    else:
        idx = data.find(USE_STRICT_ANCHOR)
        if not (0 <= idx <= 500):
            log("ERROR neither /*zro*/ nor 'use strict'; found near head")
            return False
        insert_at = idx + len(USE_STRICT_ANCHOR)
        log("route-override marker absent; anchoring after 'use strict'")
    zcjs.write_bytes(data[:insert_at] + line + data[insert_at:])
    log("injected require line into zcode.cjs")
    return True


def load_token() -> str:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tf = DATA_DIR / "auth-token"
    if tf.exists():
        t = tf.read_text(encoding="utf-8").strip()
        if t:
            return t
    t = secrets.token_hex(32)
    if "</" in t:  # must not close the script tag it is injected into
        t = secrets.token_hex(32)
    tf.write_text(t, encoding="utf-8")
    log("generated auth token -> " + str(tf))
    return t


def inject_ui(asar_root: Path, ui_js: Path) -> bool:
    html_path = asar_root / "out" / "renderer" / "index.html"
    if not html_path.exists():
        log("ERROR renderer/index.html not found under " + str(asar_root))
        return False
    js = ui_js.read_text(encoding="utf-8", newline="")
    if TOKEN_PLACEHOLDER not in js:
        log("ERROR ui_pin.js missing token placeholder " + TOKEN_PLACEHOLDER)
        return False
    token = load_token()
    js = js.replace(TOKEN_PLACEHOLDER, repr(token))
    tag = UI_MARKER + "\n" + js + "\n</script>"
    html = html_path.read_text(encoding="utf-8", newline="")
    idx = html.find(UI_MARKER)
    if idx >= 0:
        end = html.find("</script>", idx)
        if end < 0:
            log("ERROR marker without closing script tag, abort")
            return False
        html = html[:idx] + tag + html[end + len("</script>"):]
        log("replaced existing zcode-pin-ui block")
    else:
        body_end = html.rfind("</body>")
        if body_end < 0:
            log("ERROR </body> not found")
            return False
        html = html[:body_end] + tag + "\n" + html[body_end:]
        log("inserted zcode-pin-ui block before </body>")
    html_path.write_text(html, encoding="utf-8", newline="")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="extracted asar root")
    ap.add_argument("--zcode-cjs", default=None, help="path to resources/glm/zcode.cjs")
    ap.add_argument("--install-root", default=None, help="ZCode install root (unused)")
    args = ap.parse_args()

    asar_root = Path(args.dir)
    ui_js = Path(__file__).resolve().parent / "assets" / "ui_pin.js"
    wrapper_js = Path(__file__).resolve().parent / "assets" / "pin-wrapper.js"

    zcjs_done = True
    if args.zcode_cjs:
        deployed = deploy_wrapper(wrapper_js)
        zcjs_done = inject_zcode_cjs(Path(args.zcode_cjs), deployed)
    ui_done = inject_ui(asar_root, ui_js)
    return 0 if (zcjs_done and ui_done) else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""pin module — directory-mode uninstaller for the ZCode Mod Kit.

Surgical removal: deletes only this module's injected line (zcode.cjs) and its
<script id="zcode-pin-ui"> block (renderer/index.html); never touches other modules.
The auth token and pin data under ~/.zcode/plugins/pin/ are left intact.

Usage:
  python uninject.py --dir <extracted-asar-root> [--zcode-cjs <path>]

Standard library only. All output lines are prefixed with [pin].
"""
import sys, argparse
from pathlib import Path

WRAPPER_MARKER = b"/*zpin*/"
UI_MARKER = '<script id="zcode-pin-ui">'


def log(msg):
    print("[pin] " + msg)


def uninject_zcode_cjs(zcjs: Path) -> bool:
    if not zcjs.exists():
        log("SKIP zcode.cjs not found, nothing to remove")
        return True
    data = zcjs.read_bytes()
    if WRAPPER_MARKER not in data:
        log("SKIP pin require line not present")
        return True
    m = data.find(WRAPPER_MARKER)
    ls = data.rfind(b"try{require(", 0, m)
    if ls < 0 or m - ls > 400:
        log("ERROR unknown /*zpin*/ form in zcode.cjs; refusing to guess")
        return False
    data = data[:ls] + data[m + len(WRAPPER_MARKER):]
    zcjs.write_bytes(data)
    log("removed require line from zcode.cjs")
    return True


def uninject_ui(asar_root: Path) -> bool:
    html_path = asar_root / "out" / "renderer" / "index.html"
    if not html_path.exists():
        log("SKIP renderer/index.html not found")
        return True
    html = html_path.read_text(encoding="utf-8", newline="")
    idx = html.find(UI_MARKER)
    if idx < 0:
        log("SKIP zcode-pin-ui block not present")
        return True
    end = html.find("</script>", idx)
    if end < 0:
        log("ERROR marker without closing script tag, abort")
        return False
    tail = end + len("</script>")
    if tail < len(html) and html[tail] == "\n":
        tail += 1  # consume the trailing newline the injector appended
    html = html[:idx] + html[tail:]
    html_path.write_text(html, encoding="utf-8", newline="")
    log("removed zcode-pin-ui block")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="extracted asar root")
    ap.add_argument("--zcode-cjs", default=None, help="path to resources/glm/zcode.cjs")
    args = ap.parse_args()

    asar_root = Path(args.dir)

    ok1 = True
    if args.zcode_cjs:
        ok1 = uninject_zcode_cjs(Path(args.zcode_cjs))
    ok2 = uninject_ui(asar_root)
    return 0 if (ok1 and ok2) else 1


if __name__ == "__main__":
    sys.exit(main())

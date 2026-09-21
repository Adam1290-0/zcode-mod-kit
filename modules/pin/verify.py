#!/usr/bin/env python3
"""pin module — injection verifier for the ZCode Mod Kit.

Exit 0 = fully injected; non-zero = missing pieces (names printed to stdout).
Checks:
- zcode.cjs contains the /*zpin*/ require line (only when --zcode-cjs given)
- renderer/index.html contains the zcode-pin-ui block AND the token placeholder
  was replaced (no '__ZPIN_TOKEN__' residue)

Usage:
  python verify.py --dir <extracted-asar-root> [--zcode-cjs <path>]

Standard library only. All output lines are prefixed with [pin].
"""
import sys, argparse
from pathlib import Path

WRAPPER_MARKER = b"/*zpin*/"
UI_MARKER = '<script id="zcode-pin-ui">'
TOKEN_PLACEHOLDER = "'__ZPIN_TOKEN__'"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="extracted asar root")
    ap.add_argument("--zcode-cjs", default=None, help="path to resources/glm/zcode.cjs")
    args = ap.parse_args()

    missing = []

    if args.zcode_cjs:
        zcjs = Path(args.zcode_cjs)
        if not zcjs.exists():
            missing.append("zcode-cjs-missing")
        elif WRAPPER_MARKER not in zcjs.read_bytes():
            missing.append("zcode-cjs-marker")

    html_path = Path(args.dir) / "out" / "renderer" / "index.html"
    if not html_path.exists():
        missing.append("index-html-missing")
    else:
        html = html_path.read_text(encoding="utf-8", newline="")
        if UI_MARKER not in html:
            missing.append("ui-block")
        if TOKEN_PLACEHOLDER in html:
            missing.append("token-unreplaced")

    if missing:
        print("[pin] verify FAIL: " + ", ".join(missing))
        return 1
    print("[pin] verify OK: fully injected")
    return 0


if __name__ == "__main__":
    sys.exit(main())

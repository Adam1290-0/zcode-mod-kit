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
import sys, argparse, os
from pathlib import Path

DATA_DIR = Path(os.path.expanduser("~/.zcode/plugins/pin"))
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

    # Runtime wrapper freshness. The kit's SKIP gate trusts this verifier, and
    # the wrapper is only deployed by inject.py - so without this check a
    # re-install keeps an outdated ~/.zcode/plugins/pin wrapper indefinitely
    # (the 2026-09-28 "repo fixed, machine never updated" failure class).
    asset = Path(__file__).resolve().parent / "assets" / "pin-wrapper.js"
    deployed = DATA_DIR / "pin-wrapper.js"
    if not deployed.exists():
        missing.append("runtime-wrapper-missing")
    elif deployed.read_bytes() != asset.read_bytes():
        missing.append("runtime-wrapper-stale")
    core_asset = Path(__file__).resolve().parent / "assets" / "pin-core.js"
    core_deployed = DATA_DIR / "pin-core.js"
    if core_asset.exists():
        if not core_deployed.exists():
            missing.append("runtime-core-missing")
        elif core_deployed.read_bytes() != core_asset.read_bytes():
            missing.append("runtime-core-stale")

    if missing:
        print("[pin] verify FAIL: " + ", ".join(missing))
        return 1
    print("[pin] verify OK: fully injected")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""skin-manager injection verifier.

Checks that <dir>/out/renderer/index.html contains the zcode-skin-ui script
block AND that its payload is byte-identical to assets/ui_skin.js (guards
against a stale older version of the block).

Contract (mod-kit spec 2.2):
  python verify.py --dir <extracted-asar-dir> [--zcode-cjs <path>]
  exit 0 = injected and complete; exit 1 = not injected / stale payload.
"""
import argparse
import re
import sys
from pathlib import Path

MARKER = '<script id="zcode-skin-ui">'
BLOCK_RE = re.compile(r'<script id="zcode-skin-ui">(.*?)</script>', re.S)


def main() -> None:
    ap = argparse.ArgumentParser(description="skin-manager verifier")
    ap.add_argument("--dir", required=True, help="extracted asar directory")
    ap.add_argument("--zcode-cjs", help="unused by this module (targets=asar only)")
    args = ap.parse_args()

    html_path = Path(args.dir) / "out" / "renderer" / "index.html"
    js_path = Path(__file__).parent / "assets" / "ui_skin.js"

    if not html_path.is_file():
        print(f"[skin-manager] FAIL: index.html not found: {html_path}")
        return 1

    html = html_path.read_text(encoding="utf-8")
    m = BLOCK_RE.search(html)
    if not m:
        print("[skin-manager] FAIL: zcode-skin-ui block not found (not injected)")
        return 1

    # Payload freshness: block content must equal assets/ui_skin.js exactly.
    expected = js_path.read_text(encoding="utf-8").strip()
    actual = m.group(1).strip()
    if actual != expected:
        print("[skin-manager] FAIL: block payload differs from assets/ui_skin.js (stale version)")
        return 1

    print("[skin-manager] OK: injected, payload matches assets/ui_skin.js")
    return 0


if __name__ == "__main__":
    sys.exit(main())

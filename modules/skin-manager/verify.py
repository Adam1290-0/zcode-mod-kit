#!/usr/bin/env python3
"""skin-manager injection verifier.

Checks that <dir>/out/renderer/index.html contains the zcode-skin-ui script
block AND that its payload is byte-identical to assets/ui_skin.js (guards
against a stale older version of the block).

Contract (mod-kit spec 2.2):
  python verify.py --dir <extracted-asar-dir> [--zcode-cjs <path>] [--kit-version <ver>]
  exit 0 = injected and payload matches assets
  exit 2 = injected but STALE (block present, contents differ)
  exit 1 = not injected at all

The 0/1/2 split matters: the installer's skip gate uses it to tell "nothing to
do" from "there is an old block to replace or remove". Reporting a stale block
as 1 (the pre-2026-11-12 behaviour) made `uninstall.bat` skip this module
entirely and leave a live skin block inside app.asar.
"""
import argparse
import json
import re
import sys
from pathlib import Path

MARKER = '<script id="zcode-skin-ui">'
BLOCK_RE = re.compile(r'<script id="zcode-skin-ui">(.*?)</script>', re.S)


def main() -> None:
    ap = argparse.ArgumentParser(description="skin-manager verifier")
    ap.add_argument("--dir", required=True, help="extracted asar directory")
    ap.add_argument("--zcode-cjs", help="unused by this module (targets=asar only)")
    ap.add_argument("--kit-version", default=None,
                    help="expected baked mod-kit version (update banner)")
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

    # Payload freshness: block content must equal assets/ui_skin.js exactly,
    # modulo the kit-version baking (--kit-version replaces the placeholder
    # the same way inject.py does; without it the placeholder must survive).
    expected = js_path.read_text(encoding="utf-8").strip()
    if args.kit_version:
        expected = expected.replace('"__ZCKIT_VERSION__"',
                                    json.dumps(args.kit_version))
    actual = m.group(1).strip()
    if actual != expected:
        print("[skin-manager] STALE: block payload differs from assets/ui_skin.js "
              "(re-deploy on install, remove on uninstall)")
        return 2

    print("[skin-manager] OK: injected, payload matches assets/ui_skin.js")
    return 0


if __name__ == "__main__":
    sys.exit(main())

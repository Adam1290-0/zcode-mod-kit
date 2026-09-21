#!/usr/bin/env python3
"""skin-manager directory-mode uninjector.

Removes ONLY the <script id="zcode-skin-ui">...</script> block (plus its
trailing newline) from <dir>/out/renderer/index.html. Never touches any
other module's injection.

Contract (mod-kit spec 2.2):
  python uninject.py --dir <extracted-asar-dir> [--zcode-cjs <path>]
"""
import argparse
import re
import sys
from pathlib import Path

BLOCK_RE = re.compile(r'<script id="zcode-skin-ui">.*?</script>\n?', re.S)


def fail(msg: str) -> None:
    print(f"[skin-manager] ERROR: {msg}")
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="skin-manager directory-mode uninjector")
    ap.add_argument("--dir", required=True, help="extracted asar directory")
    ap.add_argument("--zcode-cjs", help="unused by this module (targets=asar only)")
    args = ap.parse_args()

    html_path = Path(args.dir) / "out" / "renderer" / "index.html"
    if not html_path.is_file():
        fail(f"index.html not found: {html_path}")

    html = html_path.read_text(encoding="utf-8")
    new_html, n = BLOCK_RE.subn("", html)
    if n == 0:
        print("[skin-manager] nothing to remove (not injected)")
        return
    if n > 1:
        # Should be impossible (inject is idempotent), but guard anyway.
        fail(f"expected 1 block, found {n}; aborting without writing")

    html_path.write_text(new_html, encoding="utf-8")
    print(f"[skin-manager] removed skin block from {html_path}")


if __name__ == "__main__":
    main()

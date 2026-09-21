#!/usr/bin/env python3
"""skin-manager directory-mode injector.

Injects ui_skin.js into <dir>/out/renderer/index.html as a
<script id="zcode-skin-ui"> block before </body>.

Contract (mod-kit spec 2.2):
  python inject.py --dir <extracted-asar-dir> [--zcode-cjs <path>] [--install-root <path>]
  - Idempotent: if marker already present, print [SKIP] and exit 0.
  - Surgical: only touches the zcode-skin-ui script block; never other modules.
  - Zero third-party deps. English comments. [skin-manager] log prefix.
  - Fails with exit != 0 and a concrete message on any error.
"""
import argparse
import re
import sys
from pathlib import Path

MARKER = '<script id="zcode-skin-ui">'
# Non-greedy to the first </script>: safe because ui_skin.js contains no
# "</script>" literal (asserted below at runtime as well).
BLOCK_RE = re.compile(r'<script id="zcode-skin-ui">.*?</script>\n?', re.S)
TAG_END = "</body>"


def fail(msg: str) -> None:
    print(f"[skin-manager] ERROR: {msg}")
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="skin-manager directory-mode injector")
    ap.add_argument("--dir", required=True, help="extracted asar directory")
    ap.add_argument("--zcode-cjs", help="unused by this module (targets=asar only)")
    ap.add_argument("--install-root", help="unused by this module (paths come from --dir)")
    args = ap.parse_args()

    root = Path(args.dir)
    html_path = root / "out" / "renderer" / "index.html"
    js_path = Path(__file__).parent / "assets" / "ui_skin.js"

    if not html_path.is_file():
        fail(f"index.html not found: {html_path}")
    if not js_path.is_file():
        fail(f"asset missing: {js_path}")

    js = js_path.read_text(encoding="utf-8")
    if "</script>" in js:
        fail("ui_skin.js contains '</script>' literal; block regex would be unsafe")

    html = html_path.read_text(encoding="utf-8")

    # Idempotent: marker present -> skip (do not double-inject).
    if MARKER in html:
        print("[skin-manager] [SKIP] already injected")
        return

    if TAG_END not in html:
        fail("index.html has no </body>; refusing to inject")

    tag = MARKER + "\n" + js + "\n</script>"
    new_html = html.replace(TAG_END, tag + "\n" + TAG_END, 1)
    if new_html == html:
        fail("replace produced no change")

    html_path.write_text(new_html, encoding="utf-8")
    print(f"[skin-manager] injected ui_skin.js into {html_path}")


if __name__ == "__main__":
    main()

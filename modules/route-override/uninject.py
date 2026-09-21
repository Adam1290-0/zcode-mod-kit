#!/usr/bin/env python3
"""route-override module — directory-mode uninjector.

Usage:
  python uninject.py --dir <extracted_asar_dir> [--zcode-cjs <path>]

Removes ONLY this module's injections:
  - the /*zro*/ require line in zcode.cjs (file-level)
  - the <script id="zcode-route-override-ui"> block in out/renderer/index.html

Never touches other modules' injections. auth-token / route-overrides.json are
runtime files and are left in place on purpose.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inject import (  # noqa: E402
    PREFIX,
    REQUIRE_MARKER,
    RENDERER_MARKER,
    USE_STRICT,
    uninject_zcode_cjs,
    uninject_renderer,
    read_raw,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="route-override directory-mode uninjector")
    ap.add_argument("--dir", required=True, help="extracted asar out directory")
    ap.add_argument("--zcode-cjs", default=None, help="path to resources/glm/zcode.cjs")
    args = ap.parse_args()

    out_dir = Path(args.dir)
    if not out_dir.exists():
        print(f"{PREFIX} [ERROR] --dir not found: {out_dir}")
        return 1

    try:
        if args.zcode_cjs:
            cjs_path = Path(args.zcode_cjs)
            if cjs_path.exists():
                uninject_zcode_cjs(cjs_path)
            else:
                print(f"{PREFIX} zcode.cjs not found at {cjs_path}, skip file-level removal")

        uninject_renderer(out_dir)
    except Exception as e:
        print(f"{PREFIX} [ERROR] {e}")
        return 1

    # Post-check: markers gone.
    ok = True
    if args.zcode_cjs and Path(args.zcode_cjs).exists():
        if REQUIRE_MARKER in read_raw(Path(args.zcode_cjs)):
            print(f"{PREFIX} [ERROR] /*zro*/ still present in zcode.cjs")
            ok = False
    html_path = out_dir / "out" / "renderer" / "index.html"
    if html_path.exists() and RENDERER_MARKER in html_path.read_text(encoding="utf-8"):
        print(f"{PREFIX} [ERROR] renderer marker still present")
        ok = False

    print(f"{PREFIX} uninject {'OK' if ok else 'FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

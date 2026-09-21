#!/usr/bin/env python3
"""account-switcher directory-mode verifier (ZCode Mod Kit interface v1.0).

Exit 0 = module is fully injected in the extracted asar tree; non-zero otherwise.
Checks:
  1. out/main/zcode-account-switcher-main.mjs exists and matches assets/ byte-for-byte
  2. out/main/index.js starts with the dynamic import line
  3. out/renderer/index.html carries the renderer script block with a closing </script>
"""
import argparse
import sys
from pathlib import Path

SLUG = "account-switcher"
MAIN_IMPORT_CORE = 'import("./zcode-account-switcher-main.mjs").catch(()=>{});'
RENDERER_MARKER = '<script id="zcode-account-switcher">'


def log(msg: str) -> None:
    print(f"[{SLUG}] {msg}")


def read_raw(p: Path) -> str:
    with open(p, "r", encoding="utf-8", newline="") as f:
        return f.read()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="extracted asar root")
    ap.add_argument("--zcode-cjs", default=None, help="(unused, accepted per contract)")
    args = ap.parse_args()

    root = Path(args.dir)
    assets = Path(__file__).resolve().parent / "assets"
    main_entry = root / "out" / "main" / "index.js"
    module_file = root / "out" / "main" / "zcode-account-switcher-main.mjs"
    html_path = root / "out" / "renderer" / "index.html"

    ok = True

    # 1. module file present and identical to the asset
    if not module_file.exists():
        log("FAIL out/main/zcode-account-switcher-main.mjs missing")
        ok = False
    else:
        want = (assets / "zcode-account-switcher-main.mjs").read_bytes()
        got = module_file.read_bytes()
        if want != got:
            log("FAIL main module differs from assets copy")
            ok = False

    # 2. main entry import (accepts either newline style)
    if not main_entry.exists():
        log("FAIL out/main/index.js missing")
        ok = False
    elif not read_raw(main_entry).startswith(MAIN_IMPORT_CORE):
        log("FAIL main entry does not start with the injection import")
        ok = False

    # 3. renderer block with a closing tag
    if not html_path.exists():
        log("FAIL out/renderer/index.html missing")
        ok = False
    else:
        html = read_raw(html_path)
        idx = html.find(RENDERER_MARKER)
        if idx < 0:
            log("FAIL renderer script block missing")
            ok = False
        elif html.find("</script>", idx) < 0:
            log("FAIL renderer block has no closing </script>")
            ok = False

    if ok:
        log("verify OK")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
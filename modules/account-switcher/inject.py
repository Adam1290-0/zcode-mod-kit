#!/usr/bin/env python3
"""account-switcher directory-mode injector (ZCode Mod Kit interface v1.0).

Injects into an EXTRACTED asar tree; never extracts or repacks on its own.

Steps:
  1. copy assets/zcode-account-switcher-main.mjs -> out/main/
  2. prepend a dynamic import line to out/main/index.js
  3. insert the renderer UI script block before </body> in out/renderer/index.html

Idempotent: if every marker is already present, prints [SKIP] and exits 0.
Surgical: only touches this module's files and injection blocks.
Line endings of the two edited files are preserved exactly (newline='').
"""
import argparse
import sys
from pathlib import Path

SLUG = "account-switcher"
MAIN_IMPORT_CORE = 'import("./zcode-account-switcher-main.mjs").catch(()=>{});'
MAIN_MARKER = 'zcode-account-switcher-main.mjs'
RENDERER_MARKER = '<script id="zcode-account-switcher">'
RENDERER_ID = 'id="zcode-account-switcher"'


def log(msg: str) -> None:
    print(f"[{SLUG}] {msg}")


def read_raw(p: Path) -> str:
    # newline='' = no line-ending translation; keep bytes exactly as they are.
    with open(p, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write_raw(p: Path, s: str) -> None:
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(s)


def detect_nl(body_idx: int, html: str) -> str:
    """Newline style of the line that carries </body>, mirrored into the block."""
    if body_idx >= 2 and html[body_idx - 2 : body_idx] == "\r\n":
        return "\r\n"
    if body_idx >= 1 and html[body_idx - 1] == "\n":
        return "\n"
    return "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="extracted asar root")
    ap.add_argument("--install-root", default=None, help="(unused, accepted per contract)")
    ap.add_argument("--zcode-cjs", default=None, help="(unused, accepted per contract)")
    args = ap.parse_args()

    root = Path(args.dir)
    assets = Path(__file__).resolve().parent / "assets"
    main_entry = root / "out" / "main" / "index.js"
    module_dst = root / "out" / "main" / "zcode-account-switcher-main.mjs"
    html_path = root / "out" / "renderer" / "index.html"

    for p in (main_entry, html_path):
        if not p.exists():
            log(f"[ERROR] required file missing: {p}")
            return 1
    for a in ("zcode-account-switcher-main.mjs", "ui_accounts.js"):
        if not (assets / a).exists():
            log(f"[ERROR] asset missing: {assets / a}")
            return 1

    # Idempotent gate: all markers already present -> skip.
    entry_src = read_raw(main_entry)
    html = read_raw(html_path)
    if MAIN_MARKER in entry_src and RENDERER_ID in html and module_dst.exists():
        log("[SKIP] already injected")
        return 0

    # 1. copy main-process module
    write_raw(module_dst, read_raw(assets / "zcode-account-switcher-main.mjs"))
    log(f"copied main module -> out/main/{module_dst.name}")

    # 2. prepend dynamic import (tolerates other modules' prepended lines)
    if MAIN_MARKER not in entry_src:
        # Match the file's own newline style so uninject can restore bytes.
        nl = "\r\n" if "\r\n" in entry_src[:4000] else "\n"
        write_raw(main_entry, MAIN_IMPORT_CORE + nl + entry_src)
        log("main entry patched (import prepended)")
    else:
        log("main entry already patched")

    # 3. renderer script block before </body>
    if RENDERER_ID in html:
        log("renderer script already present")
    else:
        body_idx = html.find("</body>")
        if body_idx < 0:
            log("[ERROR] </body> not found in out/renderer/index.html")
            return 1
        nl = detect_nl(body_idx, html)
        js = read_raw(assets / "ui_accounts.js")
        block = nl.join([RENDERER_MARKER, js, "</script>"]) + nl
        write_raw(html_path, html[:body_idx] + block + html[body_idx:])
        log("renderer script injected before </body>")

    log("inject complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
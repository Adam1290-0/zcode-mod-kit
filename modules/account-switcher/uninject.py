#!/usr/bin/env python3
"""account-switcher directory-mode uninstaller (ZCode Mod Kit interface v1.0).

Removes exactly what inject.py added, from an EXTRACTED asar tree:
  1. delete out/main/zcode-account-switcher-main.mjs
  2. strip the prepended dynamic import line from out/main/index.js
  3. remove the renderer <script id="zcode-account-switcher"> block

Marker-based and surgical: no other module's injections are touched.
Line endings are preserved exactly (newline='').
"""
import argparse
import sys
from pathlib import Path

SLUG = "account-switcher"
MAIN_IMPORT_CORE = 'import("./zcode-account-switcher-main.mjs").catch(()=>{});'
MAIN_MARKER = 'zcode-account-switcher-main.mjs'
RENDERER_MARKER = '<script id="zcode-account-switcher">'


def log(msg: str) -> None:
    print(f"[{SLUG}] {msg}")


def read_raw(p: Path) -> str:
    with open(p, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write_raw(p: Path, s: str) -> None:
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(s)


def remove_block(html: str, marker: str) -> str:
    """Cut one <script>...</script> block starting at `marker`, plus the
    newline the injector appended right after </script>.
    """
    idx = html.find(marker)
    if idx < 0:
        return html
    end = html.find("</script>", idx)
    if end < 0:
        raise ValueError("marker found but no closing </script>")
    end += len("</script>")
    # consume the line break right after </script> if present
    if html[end : end + 2] == "\r\n":
        end += 2
    elif end < len(html) and html[end] == "\n":
        end += 1
    return html[:idx] + html[end:]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="extracted asar root")
    ap.add_argument("--zcode-cjs", default=None, help="(unused, accepted per contract)")
    args = ap.parse_args()

    root = Path(args.dir)
    main_entry = root / "out" / "main" / "index.js"
    module_file = root / "out" / "main" / "zcode-account-switcher-main.mjs"
    html_path = root / "out" / "renderer" / "index.html"

    for p in (main_entry, html_path):
        if not p.exists():
            log(f"[ERROR] required file missing: {p}")
            return 1

    removed_any = False

    # 1. module file
    if module_file.exists():
        module_file.unlink()
        log("removed out/main/zcode-account-switcher-main.mjs")
        removed_any = True

    # 2. main entry import line (accepts either newline style)
    src = read_raw(main_entry)
    if src.startswith(MAIN_IMPORT_CORE):
        rest = src[len(MAIN_IMPORT_CORE):]
        if rest.startswith("\r\n"):
            rest = rest[2:]
        elif rest.startswith("\n"):
            rest = rest[1:]
        write_raw(main_entry, rest)
        log("main entry import line removed")
        removed_any = True
    elif MAIN_MARKER in src:
        log("[ERROR] import marker present but not in the expected prepended form; aborting")
        return 1

    # 3. renderer block
    html = read_raw(html_path)
    if RENDERER_MARKER in html:
        try:
            html = remove_block(html, RENDERER_MARKER)
        except ValueError as e:
            log(f"[ERROR] {e}")
            return 1
        write_raw(html_path, html)
        log("renderer script block removed")
        removed_any = True

    if not removed_any:
        log("[SKIP] nothing to remove (not injected)")
    else:
        log("uninject complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
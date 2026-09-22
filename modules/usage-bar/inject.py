#!/usr/bin/env python3
"""usage-bar module (zcode-token-usage-statusbar) - directory-mode injector.

Appends one dynamic-import line to <dir>/out/main/index.js pointing at the
self-contained runtime dir (~/.zcode/plugins/usage-bar/), which holds the
loader (inject-main.cjs), overlay and the resident python pump (zusage.py).

Usage:
  python inject.py --dir <extracted-asar-dir> [--zcode-cjs <path>] [--install-root <root>]

Idempotent, surgical: only this module's injection line is ever touched.
Old lines pointing at other directories are replaced on re-injection.
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

SLUG = "usage-bar"
RUNTIME_DIR = Path(os.path.expanduser("~/.zcode/plugins/usage-bar"))
RUNTIME_FILES = ("inject-main.cjs", "overlay.js", "zusage.py")


def log(msg):
    print(f"[{SLUG}] {msg}")


def line_for(runtime: Path) -> bytes:
    url = (runtime / "inject-main.cjs").as_uri()
    return ('\n;import("{u}").then(() => null, (e) => console.error("[zusage] load failed", e));'
            .format(u=url).encode())


def strip_line(data: bytes):
    """Cut one usage-bar injection line; returns (data, removed_count).

    The line has a fixed shape and its only semicolon is the trailing one,
    so plain string surgery is used instead of a regex.
    """
    anchor = b'inject-main.cjs")'
    idx = data.find(anchor)
    if idx < 0:
        return data, 0
    start = data.rfind(b';import(', 0, idx) - 1  # the leading \n of '\n;import('
    if start < 0:
        return data, 0
    end = data.find(b';', idx)
    if end < 0:
        return data, 0
    return data[:start] + data[end + 1:], 1


def main() -> int:
    ap = argparse.ArgumentParser(description=f"{SLUG}: directory-mode injector")
    ap.add_argument("--dir", required=True, help="extracted asar root")
    ap.add_argument("--zcode-cjs", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--install-root", default=None, help=argparse.SUPPRESS)
    args = ap.parse_args()

    root = Path(args.dir)
    entry = root / "out" / "main" / "index.js"
    if not entry.is_file():
        log(f"[ERROR] out/main/index.js not found under {root}")
        return 1

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    assets = Path(__file__).resolve().parent / "assets"
    for name in RUNTIME_FILES:
        shutil.copy2(assets / name, RUNTIME_DIR / name)
    cfg = RUNTIME_DIR / "config.json"
    if not cfg.exists() and (assets / "config.example.json").exists():
        shutil.copy2(assets / "config.example.json", cfg)
    log(f"runtime deployed -> {RUNTIME_DIR}")

    data = entry.read_bytes()
    new_line = line_for(RUNTIME_DIR)
    if new_line in data:
        log("[SKIP] already injected")
        return 0
    # strip any old line (pointing elsewhere) before appending the fresh one
    data, n = strip_line(data)
    if n:
        log("replaced old injection line (redeploy)")
    entry.write_bytes(data + new_line)
    log("injected dynamic import line into out/main/index.js")
    return 0


if __name__ == "__main__":
    sys.exit(main())

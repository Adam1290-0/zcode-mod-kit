#!/usr/bin/env python3
"""usage-bar module - verify injection state (directory mode). Exit 0 = injected."""
import argparse
import os
import sys
from pathlib import Path

SLUG = "usage-bar"
LINE_ANCHOR = b'inject-main.cjs")'
RUNTIME_DIR = Path(os.path.expanduser("~/.zcode/plugins/usage-bar"))
RUNTIME_FILES = ("inject-main.cjs", "overlay.js", "zusage.py")


def main() -> int:
    ap = argparse.ArgumentParser(description=f"{SLUG}: verify injection state")
    ap.add_argument("--dir", required=True, help="extracted asar root")
    ap.add_argument("--zcode-cjs", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--install-root", default=None, help=argparse.SUPPRESS)
    args = ap.parse_args()

    entry = Path(args.dir) / "out" / "main" / "index.js"
    if not entry.is_file():
        print(f"[{SLUG}] not injected (no index.js)")
        return 1
    injected = LINE_ANCHOR in entry.read_bytes()
    if not injected:
        print(f"[{SLUG}] not injected")
        return 1

    # The injected line only points at the runtime dir. If those files are
    # missing or stale the module is broken while still reading as "injected",
    # and the skip gate would never re-deploy an updated overlay.
    assets = Path(__file__).resolve().parent / "assets"
    ok = True
    for name in RUNTIME_FILES:
        p = RUNTIME_DIR / name
        if not p.is_file():
            print(f"[{SLUG}] FAIL: runtime file missing: {p}")
            ok = False
            continue
        src = assets / name
        if src.is_file() and p.read_bytes() != src.read_bytes():
            print(f"[{SLUG}] FAIL: runtime file STALE (differs from assets): {p}")
            ok = False
    if ok:
        print(f"[{SLUG}] injected (runtime OK)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""usage-bar module - verify injection state (directory mode). Exit 0 = injected."""
import argparse
import sys
from pathlib import Path

SLUG = "usage-bar"
LINE_ANCHOR = b'inject-main.cjs")'


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
    print(f"[{SLUG}] " + ("injected" if injected else "not injected"))
    return 0 if injected else 1


if __name__ == "__main__":
    sys.exit(main())

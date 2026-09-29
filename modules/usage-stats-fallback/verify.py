#!/usr/bin/env python3
"""usage-stats-fallback: zcode-cjs verifier for zcode-mod-kit.

Exit 0 means both markers are present (injected). Any other state exits non-zero.
"""
import argparse
import sys
from pathlib import Path

SLUG = "usage-stats-fallback"
MARKER1 = b"zusage-fb-day"
MARKER2 = b"zusage-fb-merge"

def main() -> None:
    ap = argparse.ArgumentParser(description=f"{SLUG}: verifier")
    ap.add_argument("--dir", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--zcode-cjs", default=None, help="path to resources/glm/zcode.cjs")
    ap.add_argument("--install-root", default=None, help=argparse.SUPPRESS)
    args = ap.parse_args()
    if not args.zcode_cjs:
        print(f"[{SLUG}] FAIL: missing --zcode-cjs path")
        sys.exit(1)
    tpath = Path(args.zcode_cjs).resolve()
    if not tpath.is_file():
        print(f"[{SLUG}] FAIL: target file not found: {tpath}")
        sys.exit(1)
    data = tpath.read_bytes()
    ok = True
    if MARKER1 not in data:
        print(f"[{SLUG}] FAIL: marker1 (day fallback) not found")
        ok = False
    if MARKER2 not in data:
        print(f"[{SLUG}] FAIL: marker2 (totals merge) not found")
        ok = False
    if ok:
        print(f"[{SLUG}] verified: usage fallback injected")
        return 0
    return 1

if __name__ == "__main__":
    sys.exit(main())
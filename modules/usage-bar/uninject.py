#!/usr/bin/env python3
"""usage-bar module - remove the zusage injection line (directory mode)."""
import argparse
import sys
from pathlib import Path

SLUG = "usage-bar"


def strip_line(data: bytes):
    """Cut one usage-bar injection line; returns (data, removed_count)."""
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
    ap = argparse.ArgumentParser(description=f"{SLUG}: remove injection")
    ap.add_argument("--dir", required=True, help="extracted asar root")
    ap.add_argument("--zcode-cjs", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--install-root", default=None, help=argparse.SUPPRESS)
    args = ap.parse_args()

    entry = Path(args.dir) / "out" / "main" / "index.js"
    if not entry.is_file():
        print(f"[{SLUG}] [ERROR] out/main/index.js not found")
        return 1
    data = entry.read_bytes()
    new_data, n = strip_line(data)
    if n == 0:
        print(f"[{SLUG}] [SKIP] injection line not present")
        return 0
    entry.write_bytes(new_data)
    print(f"[{SLUG}] removed injection line")
    return 0


if __name__ == "__main__":
    sys.exit(main())

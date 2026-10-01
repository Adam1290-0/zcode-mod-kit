#!/usr/bin/env python3
"""zombie-cleanup: zcode-cjs verifier for zcode-mod-kit.

Exit 0 means the marker is present (injected). Any other state exits non-zero.
"""
import argparse
import sys
from pathlib import Path

SLUG = "zombie-cleanup"
MARKER = b"zcode-zombie-cleanup"
CLEANUP_SCRIPT = "C:/Users/adamt/.zcode/scripts/cleanup_mcp_zombies.ps1"
# Pre-kit manual patch (scripts/patch_zcode_mcp_cleanup.py) injected the same
# payload without the marker. Functionally identical -> count as injected.
LEGACY_CORE = (
    b'require("child_process").spawn("powershell",'
    b'["-NoProfile","-ExecutionPolicy","Bypass","-WindowStyle","Hidden",'
    b'"-File","' + CLEANUP_SCRIPT.encode() + b'"'
)


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
    if MARKER not in data and LEGACY_CORE not in data:
        print(f"[{SLUG}] FAIL: cleanup trigger not found")
        sys.exit(1)
    print(f"[{SLUG}] verified: cleanup trigger injected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
#!/usr/bin/env python3
"""zombie-cleanup: zcode-cjs uninjector for zcode-mod-kit.

Restores the original shutdown handler by removing the injected trigger.
"""
import argparse
import sys
from pathlib import Path

SLUG = "zombie-cleanup"
ANCHOR = b"f(),n(eNi(_))"
MARKER = b"zcode-zombie-cleanup"

CLEANUP_SCRIPT = "C:/Users/adamt/.zcode/scripts/cleanup_mcp_zombies.ps1"
INSERT = (
    b"/*zcode-zombie-cleanup*/"
    b"function(){try{require(\"child_process\").spawn(\"powershell\","
    b"[\"-NoProfile\",\"-ExecutionPolicy\",\"Bypass\",\"-WindowStyle\",\"Hidden\","
    b"\"-File\",\"" + CLEANUP_SCRIPT.encode() + b"\",\"-Tag\",\"zcode-exit\"],"
    b"{detached:true,stdio:\"ignore\"}).unref()}catch(e){}}(),"
)


def main() -> None:
    ap = argparse.ArgumentParser(description=f"{SLUG}: uninjector")
    ap.add_argument("--dir", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--zcode-cjs", default=None, help="path to resources/glm/zcode.cjs")
    ap.add_argument("--install-root", default=None, help=argparse.SUPPRESS)
    args = ap.parse_args()
    if not args.zcode_cjs:
        print(f"[{SLUG}] missing --zcode-cjs path")
        sys.exit(1)
    tpath = Path(args.zcode_cjs).resolve()
    if not tpath.is_file():
        print(f"[{SLUG}] target file not found: {tpath}")
        sys.exit(1)
    data = tpath.read_bytes()
    if MARKER not in data:
        print(f"[{SLUG}] [SKIP] not injected")
        return
    new = data.replace(INSERT + ANCHOR, ANCHOR, 1)
    if MARKER in new:
        print(f"[{SLUG}] [ERROR] marker still present after uninject")
        sys.exit(1)
    tpath.write_bytes(new)
    print(f"[{SLUG}] restored: cleanup trigger removed from shutdown handler")


if __name__ == "__main__":
    main()
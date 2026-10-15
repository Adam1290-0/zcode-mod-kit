#!/usr/bin/env python3
"""zombie-cleanup: zcode-cjs uninjector for zcode-mod-kit.

Restores the original shutdown handler by removing the injected trigger.
Supports both minified symbol generations (eNi <= 3.14.x, z7i 3.15.x) and
the pre-kit legacy unmarked patch.
"""
import argparse
import sys
from pathlib import Path

SLUG = "zombie-cleanup"
MARKER = b"zcode-zombie-cleanup"
ANCHOR_314 = b"f(),n(eNi(_))"
ANCHOR_315 = b"f(),n(z7i(_))"

CLEANUP_SCRIPT = "C:/Users/adamt/.zcode/scripts/cleanup_mcp_zombies.ps1"


def _payload() -> bytes:
    return (
        b"function(){try{require(\"child_process\").spawn(\"powershell\","
        b"[\"-NoProfile\",\"-ExecutionPolicy\",\"Bypass\",\"-WindowStyle\",\"Hidden\","
        b"\"-File\",\"" + CLEANUP_SCRIPT.encode() + b"\",\"-Tag\",\"zcode-exit\"],"
        b"{detached:true,stdio:\"ignore\"}).unref()}catch(e){}}()"
    )


POOLED = _payload()
LEGACY_314 = b"f()," + POOLED + b",n(eNi(_))"
LEGACY_315 = b"f()," + POOLED + b",n(z7i(_))"


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

    changed = False
    for anchor in (ANCHOR_314, ANCHOR_315):
        # marked form: marker + payload + ',' + anchor
        marked_insert = b"/*zcode-zombie-cleanup*/" + POOLED + b","
        if marked_insert + anchor in data:
            data = data.replace(marked_insert + anchor, anchor, 1)
            changed = True
            break
        # legacy unmarked form: f(), payload, n(...)
        legacy = b"f()," + POOLED + b",n(" + (b"eNi(_))" if anchor == ANCHOR_314 else b"z7i(_))")
        if legacy in data:
            data = data.replace(legacy, anchor, 1)
            changed = True
            break

    if not changed:
        print(f"[{SLUG}] [SKIP] not injected")
        return
    if MARKER in data:
        print(f"[{SLUG}] [ERROR] marker still present after uninject")
        sys.exit(1)
    tpath.write_bytes(data)
    print(f"[{SLUG}] restored: cleanup trigger removed from shutdown handler")


if __name__ == "__main__":
    main()
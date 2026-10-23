#!/usr/bin/env python3
"""zombie-cleanup: zcode-cjs uninjector for zcode-mod-kit.

Restores the original shutdown handler by removing the injected trigger.
Supports every known minified symbol generation (eNi <= 3.14.x, z7i 3.15.x,
TYi 3.16.2, RYi 3.16.3) and the pre-kit legacy unmarked patch.
"""
import argparse
import sys
from pathlib import Path

SLUG = "zombie-cleanup"
MARKER = b"zcode-zombie-cleanup"
ANCHOR_314 = b"f(),n(eNi(_))"
ANCHOR_315 = b"f(),n(z7i(_))"
ANCHOR_316 = b"f(),n(TYi(_))"
ANCHOR_3163 = b"f(),n(RYi(_))"
ANCHORS = (ANCHOR_314, ANCHOR_315, ANCHOR_316, ANCHOR_3163)

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
LEGACY_316 = b"f()," + POOLED + b",n(TYi(_))"
LEGACY_3163 = b"f()," + POOLED + b",n(RYi(_))"


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
    for anchor in ANCHORS:
        # marked form: marker + payload + ',' + anchor
        marked_insert = b"/*zcode-zombie-cleanup*/" + POOLED + b","
        if marked_insert + anchor in data:
            data = data.replace(marked_insert + anchor, anchor, 1)
            changed = True
            break
        # legacy unmarked form: f(), payload, n(<inner>) — the inner name
        # follows whichever anchor matched (eNi/z7i/TYi), so derive it from
        # the anchor itself rather than hard-coding a two-way ternary.
        legacy = b"f()," + POOLED + b",n(" + anchor[len(b"f(),n("):]
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
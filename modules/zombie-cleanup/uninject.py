#!/usr/bin/env python3
"""zombie-cleanup: zcode-cjs uninjector for zcode-mod-kit.

Restores the original shutdown handler by removing the injected trigger.
Supports every known minified symbol generation (eNi <= 3.14.x, z7i 3.15.x,
TYi 3.16.2, RYi 3.16.3, Ios 3.17.2) and the pre-kit legacy unmarked patch.
"""
import argparse
import os
import re
import sys
from pathlib import Path

SLUG = "zombie-cleanup"
MARKER = b"zcode-zombie-cleanup"
ANCHOR_314 = b"f(),n(eNi(_))"
ANCHOR_315 = b"f(),n(z7i(_))"
ANCHOR_316 = b"f(),n(TYi(_))"
ANCHOR_3163 = b"f(),n(RYi(_))"
ANCHOR_3172 = b"f(),n(Ios(_))"
ANCHOR_3180 = b"d(),n(mgs(_))"
ANCHORS = (ANCHOR_314, ANCHOR_315, ANCHOR_316, ANCHOR_3163, ANCHOR_3172,
           ANCHOR_3180)

RUNTIME_DIR = Path(os.path.expanduser("~/.zcode/plugins/zombie-cleanup"))
CLEANUP_SCRIPT_NAME = "cleanup_mcp_zombies.ps1"
CLEANUP_SCRIPT = str((RUNTIME_DIR / CLEANUP_SCRIPT_NAME).as_posix())

# Path-agnostic shape of the injected payload. Matching the exact current
# user's path is not enough: a payload injected under a different profile (or
# the pre-portability hardcoded one) carries a different -File argument and
# would stay behind forever, since uninstall is the only way to remove it.
PAYLOAD_RE = re.compile(
    rb"function\(\)\{try\{require\(\"child_process\"\)\.spawn\(\"powershell\","
    rb"\[\"-NoProfile\",\"-ExecutionPolicy\",\"Bypass\",\"-WindowStyle\",\"Hidden\","
    rb"\"-File\",\"[^\"]*cleanup_mcp_zombies\.ps1\",\"-Tag\",\"zcode-exit\"\],"
    rb"\{detached:true,stdio:\"ignore\"\}\)\.unref\(\)\}catch\(e\)\{\}\}\(\)"
)


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
LEGACY_3172 = b"f()," + POOLED + b",n(Ios(_))"


def _strip_payloads(data: bytes) -> tuple[bytes, int]:
    """Remove every injected payload regardless of the -File path it carries.

    Two shapes exist:
      marked:  /*zcode-zombie-cleanup*/<payload>,<anchor>
      legacy:  f(),<payload>,<anchor>
    The anchoring punctuation is consumed so the original anchor stays intact.
    """
    removed = 0

    def drop_marked(m: re.Match) -> bytes:
        nonlocal removed
        removed += 1
        return b""

    data = re.sub(rb"/\*zcode-zombie-cleanup\*/" + PAYLOAD_RE.pattern + rb",",
                  drop_marked, data)
    # The unregister call's symbol rotates too (f on <=3.17.2, d on 3.18.0),
    # so the legacy shape match must not assume `f()`. Capture and replay it.
    data = re.sub(rb"([A-Za-z_$][\w$]*)\(\)," + PAYLOAD_RE.pattern + rb",",
                  lambda m: m.group(1) + b"(),", data)

    return data, removed


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

    new_data, removed = _strip_payloads(data)
    if removed == 0:
        # Fall back to exact-match passes for any anchor generation whose
        # surrounding text differs from the generalised shape.
        for anchor in ANCHORS:
            marked_insert = b"/*zcode-zombie-cleanup*/" + POOLED + b","
            if marked_insert + anchor in data:
                new_data = data.replace(marked_insert + anchor, anchor, 1)
                removed = 1
                break
            # The unregister symbol rotates (f on <=3.17.2, d on 3.18.0):
            # rebuild the legacy shape from the anchor's own prefix.
            prefix, _, rest = anchor.partition(b"(),n(")
            legacy = prefix + b"()," + POOLED + b",n(" + rest
            if legacy in data:
                new_data = data.replace(legacy, anchor, 1)
                removed = 1
                break

    if removed == 0:
        print(f"[{SLUG}] [SKIP] not injected")
        return
    if MARKER in new_data:
        print(f"[{SLUG}] [ERROR] marker still present after uninject")
        sys.exit(1)
    tpath.write_bytes(new_data)
    print(f"[{SLUG}] restored: cleanup trigger removed from shutdown handler")


if __name__ == "__main__":
    main()
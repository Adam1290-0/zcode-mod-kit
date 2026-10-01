#!/usr/bin/env python3
"""zombie-cleanup: zcode-cjs injector for zcode-mod-kit.

Injects a fire-and-forget cleanup trigger into the CLI shutdown handler so
orphaned MCP child processes (wigolo / filesystem / memory / github /
sequential-thinking / acct.cjs) are killed when ZCode exits.

The injected code runs powershell cleanup_mcp_zombies.ps1 detached. The
anchor (shutdown handler body `f(),n(eNi(_))`) is byte-unique in the
clean 3.14.4 bundle; the patch is raw-byte and idempotent.
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

SLUG = "zombie-cleanup"
ANCHOR = b"f(),n(eNi(_))"
MARKER = b"zcode-zombie-cleanup"

CLEANUP_SCRIPT = "C:/Users/adamt/.zcode/scripts/cleanup_mcp_zombies.ps1"


def _payload() -> bytes:
    """The injected function(){}() snippet, shared by every patch format."""
    return (
        b"function(){try{require(\"child_process\").spawn(\"powershell\","
        b"[\"-NoProfile\",\"-ExecutionPolicy\",\"Bypass\",\"-WindowStyle\",\"Hidden\","
        b"\"-File\",\"" + CLEANUP_SCRIPT.encode() + b"\",\"-Tag\",\"zcode-exit\"],"
        b"{detached:true,stdio:\"ignore\"}).unref()}catch(e){}}()"
    )


INSERT = b"/*zcode-zombie-cleanup*/" + _payload() + b","
# 2026-09-29 the pre-kit manual patch (scripts/patch_zcode_mcp_cleanup.py)
# injected the same payload WITHOUT the marker, wedged between f() and
# n(eNi(_)). It is functionally identical; treat it as already-injected so a
# reinstall skips instead of failing on "anchor matched 0 times".
LEGACY_INSERT = b"f()," + _payload() + b",n(eNi(_))"


def log(msg: str) -> None:
    print(f"[{SLUG}] {msg}")


def fail(msg: str, code: int = 1) -> None:
    log(f"[ERROR] {msg}")
    sys.exit(code)


def node_check(data: bytes) -> bool:
    with tempfile.NamedTemporaryFile("wb", suffix=".js", delete=False) as tf:
        tf.write(data)
        path = tf.name
    try:
        proc = subprocess.run(["node", "--check", path], capture_output=True,
                              text=True, timeout=120)
        if proc.returncode != 0:
            log(f"node --check failed: {proc.stderr[:500]}")
            return False
        return True
    except FileNotFoundError:
        log("node not found, skipping syntax check")
        return True
    finally:
        Path(path).unlink(missing_ok=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=f"{SLUG}: inject cleanup trigger")
    ap.add_argument("--dir", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--zcode-cjs", default=None, help="path to resources/glm/zcode.cjs")
    ap.add_argument("--install-root", default=None, help=argparse.SUPPRESS)
    args = ap.parse_args()
    if not args.zcode_cjs:
        fail("missing --zcode-cjs path")
    tpath = Path(args.zcode_cjs).resolve()
    if not tpath.is_file():
        fail(f"target file not found: {tpath}")
    log(f"target: {tpath}")
    data = tpath.read_bytes()

    if MARKER in data:
        log("[SKIP] already injected")
        return

    # Pre-kit manual patch: payload present without the marker. Upgrading it to
    # the marked form costs an edit; the payload is byte-identical, so accept
    # it as injected and SKIP, mirroring the normal idempotency path.
    if LEGACY_INSERT in data:
        log("[SKIP] legacy unmarked patch detected; functionally identical, "
            "leaving as-is")
        return

    if data.count(ANCHOR) != 1:
        fail(f"anchor matched {data.count(ANCHOR)} times (expected 1); "
             f"refusing to inject (version drift?)", 2)

    new = data.replace(ANCHOR, INSERT + ANCHOR, 1)

    if not node_check(new):
        fail("syntax check failed; nothing written", 3)
    if MARKER not in new:
        fail("post-inject marker check failed; nothing written", 4)

    tpath.write_bytes(new)
    log("injected: cleanup trigger added to CLI shutdown handler")


if __name__ == "__main__":
    main()
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
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SLUG = "zombie-cleanup"
# Runtime home for the cleanup script. It must NOT point into this repository
# (the kit folder is movable and, for every other user, is somewhere else
# entirely) and it must NOT be an absolute path into one person's profile -
# the previous hardcoded C:/Users/<name>/... made the module silently do
# nothing on any other machine, because the spawned powershell simply failed
# to find the script.
RUNTIME_DIR = Path(os.path.expanduser("~/.zcode/plugins/zombie-cleanup"))
CLEANUP_SCRIPT_NAME = "cleanup_mcp_zombies.ps1"
CLEANUP_SCRIPT = str((RUNTIME_DIR / CLEANUP_SCRIPT_NAME).as_posix())

# ZCode renames minified symbols between releases; the shutdown call shape is
# f(),n(<exitCodeForSignal>(_)) — the inner function name has changed on every
# release: eNi (<= 3.14.x) -> z7i (3.15.x) -> TYi (3.16.2) -> RYi (3.16.3).
# All known generations are supported; exactly one must match.
ANCHOR_314 = b"f(),n(eNi(_))"
ANCHOR_315 = b"f(),n(z7i(_))"
ANCHOR_316 = b"f(),n(TYi(_))"
ANCHOR_3163 = b"f(),n(RYi(_))"
ANCHORS = (ANCHOR_314, ANCHOR_315, ANCHOR_316, ANCHOR_3163)
MARKER = b"zcode-zombie-cleanup"


def _payload_for(script: str) -> bytes:
    """The injected function(){}() snippet for a given script path."""
    return (
        b"function(){try{require(\"child_process\").spawn(\"powershell\","
        b"[\"-NoProfile\",\"-ExecutionPolicy\",\"Bypass\",\"-WindowStyle\",\"Hidden\","
        b"\"-File\",\"" + script.encode() + b"\",\"-Tag\",\"zcode-exit\"],"
        b"{detached:true,stdio:\"ignore\"}).unref()}catch(e){}}()"
    )


def _payload() -> bytes:
    """The injected snippet pointing at the portable runtime script."""
    return _payload_for(CLEANUP_SCRIPT)


# Script paths earlier kit versions hardcoded. Any injected payload still
# referencing one of these is silently dead on every machine except the
# original author's, so it is migrated in place rather than left alone.
LEGACY_SCRIPTS = ("C:/Users/adamt/.zcode/scripts/cleanup_mcp_zombies.ps1",)


def migrate_legacy_payload(data: bytes) -> tuple[bytes, bool]:
    """Repoint an already-injected payload at the portable script path.

    Returns (new_data, changed). Handles both the marked form and the older
    unmarked patches, because both embedded the same absolute path.
    """
    changed = False
    for old in LEGACY_SCRIPTS:
        old_payload = _payload_for(old)
        if old_payload in data:
            data = data.replace(old_payload, _payload())
            changed = True
    return data, changed


# Pre-kit manual patch (scripts/patch_zcode_mcp_cleanup.py) injected the same
# payload WITHOUT the marker, wedged between f() and n(...). It is functionally
# identical; treat it as already-injected so a reinstall skips instead of
# failing on "anchor matched 0 times".
LEGACY_INSERT_314 = b"f()," + _payload() + b",n(eNi(_))"
LEGACY_INSERT_315 = b"f()," + _payload() + b",n(z7i(_))"
LEGACY_INSERT_316 = b"f()," + _payload() + b",n(TYi(_))"
LEGACY_INSERT_3163 = b"f()," + _payload() + b",n(RYi(_))"


def find_anchor(data: bytes) -> bytes:
    """Return the matching anchor bytes, or None when neither matches."""
    for anchor in ANCHORS:
        if data.count(anchor) >= 1:
            return anchor
    return None


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


def deploy_script() -> Path:
    """Copy the cleanup script into the persistent runtime dir.

    The injected powershell call has to resolve on every machine, so the
    script ships with the module and is copied somewhere stable rather than
    being referenced from a per-user path in the repo.
    """
    src = Path(__file__).resolve().parent / "assets" / CLEANUP_SCRIPT_NAME
    if not src.is_file():
        fail(f"cleanup script asset missing: {src}")
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    dst = RUNTIME_DIR / CLEANUP_SCRIPT_NAME
    shutil.copy2(src, dst)
    log(f"deployed cleanup script -> {dst}")
    return dst


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
    deploy_script()
    data = tpath.read_bytes()

    # Migrate payloads that still point at a per-user hardcoded script path.
    # Must run BEFORE the idempotency gates, otherwise an old install skips
    # forever and the module stays dead on machines that are not the author's.
    data, migrated = migrate_legacy_payload(data)
    if migrated:
        if not node_check(data):
            fail("syntax check failed while migrating legacy payload; nothing written", 3)
        tpath.write_bytes(data)
        log("migrated injected payload to the portable runtime script path")

    if MARKER in data:
        log("[SKIP] already injected")
        return

    # Pre-kit manual patches: payload present without the marker (either
    # minified-symbol generation). Functionally identical — accept and SKIP.
    for legacy in (LEGACY_INSERT_314, LEGACY_INSERT_315, LEGACY_INSERT_316,
                   LEGACY_INSERT_3163):
        if legacy in data:
            log("[SKIP] legacy unmarked patch detected; functionally identical, "
                "leaving as-is")
            return

    anchor = find_anchor(data)
    if anchor is None or data.count(anchor) != 1:
        log("anchor probe: " + " ".join(
            f"{anchor[6:9].decode()}-version={data.count(anchor)}"
            for anchor in ANCHORS))
        fail("anchor matched 0 or >1 times (expected exactly 1); "
             "refusing to inject (version drift?)", 2)

    insert = b"/*zcode-zombie-cleanup*/" + _payload() + b","
    new = data.replace(anchor, insert + anchor, 1)

    if not node_check(new):
        fail("syntax check failed; nothing written", 3)
    if MARKER not in new:
        fail("post-inject marker check failed; nothing written", 4)

    tpath.write_bytes(new)
    log("injected: cleanup trigger added to CLI shutdown handler")


if __name__ == "__main__":
    main()
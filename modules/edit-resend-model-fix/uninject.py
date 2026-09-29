#!/usr/bin/env python3
"""edit-resend-model-fix: zcode-cjs uninjector for zcode-mod-kit.

Restores the original object literal by turning the idempotency comment
marker back into "modelSelection:o.intent.modelSelection,mode:o.intent.mode,
planEnabled:o.intent.planEnabled,".
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

SLUG = "edit-resend-model-fix"
OLD = b"modelSelection:o.intent.modelSelection,mode:o.intent.mode,planEnabled:o.intent.planEnabled,"
NEW = b"/*[zcode-editresend-model-fix]*/"
MARKER = b"zcode-editresend-model-fix"


def log(msg: str) -> None:
    print(f"[{SLUG}] {msg}")


def fail(msg: str, code: int = 1) -> None:
    log(f"[ERROR] {msg}")
    sys.exit(code)


def node_check(data: bytes) -> bool:
    with tempfile.NamedTemporaryFile(
        "wb", suffix=".js", delete=False
    ) as tf:
        tf.write(data)
        path = tf.name
    try:
        proc = subprocess.run(
            ["node", "--check", path], capture_output=True, text=True, timeout=120
        )
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
    ap = argparse.ArgumentParser(description=f"{SLUG}: un-inject stale-settings fix")
    ap.add_argument("--dir", default=None, help=argparse.SUPPRESS)  # accepted, unused
    ap.add_argument("--zcode-cjs", default=None, help="path to resources/glm/zcode.cjs")
    ap.add_argument("--install-root", default=None, help=argparse.SUPPRESS)  # accepted, unused
    args = ap.parse_args()

    if not args.zcode_cjs:
        fail("missing --zcode-cjs path")
    tpath = Path(args.zcode_cjs).resolve()
    if not tpath.is_file():
        fail(f"target file not found: {tpath}")

    data = tpath.read_bytes()

    if MARKER not in data:
        log("[SKIP] not injected")
        return

    new_data = data.replace(NEW, OLD, 1)

    if not node_check(new_data):
        fail("syntax check failed; nothing written", 3)
    if MARKER in new_data or new_data.count(OLD) != 1:
        fail("post-uninject content check failed; nothing written", 4)

    tpath.write_bytes(new_data)
    log("restored: stale modelSelection/mode/planEnabled re-added to SJo re-run")


if __name__ == "__main__":
    main()
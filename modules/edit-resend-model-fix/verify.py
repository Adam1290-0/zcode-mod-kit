#!/usr/bin/env python3
"""edit-resend-model-fix: zcode-cjs verifier for zcode-mod-kit.

Exit 0 means the fix is applied: marker present AND the stale
modelSelection/mode/planEnabled fields are gone from SJo's re-run.
An unpatched file (fix not applied) is a failure. Any other state exits
non-zero.
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
    ap = argparse.ArgumentParser(description=f"{SLUG}: verify injection state")
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

    has_marker = MARKER in data
    stale_present = OLD in data

    if has_marker and not stale_present:
        if not node_check(data):
            fail("syntax check failed")
        log("verified: stale modelSelection/mode/planEnabled removed from SJo re-run")
        return

    problems = []
    if not has_marker:
        problems.append("marker missing (not injected)")
    if stale_present:
        problems.append("stale modelSelection/mode/planEnabled still present")
    if not problems:
        problems.append("unknown state")
    fail("verify failed: " + "; ".join(problems))


if __name__ == "__main__":
    main()
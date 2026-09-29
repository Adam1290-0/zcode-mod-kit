#!/usr/bin/env python3
"""edit-resend-model-fix: zcode-cjs injector for zcode-mod-kit.

Removes three stale session-settings fields from the v4 canonical-intent
re-run so that "edit user query" / "retry turn" picks up the CURRENT session
model + mode + plan-enabled state instead of replaying the values captured
when the message was first sent.

Root cause (zcode.cjs, minified):
  async function SJo(...){...kJo(n,{...,modelSelection:o.intent.modelSelection,
      mode:o.intent.mode,planEnabled:o.intent.planEnabled,...},s);...}
  SJo is shared by both editUserQuery (yKa) and retryTurn (vKa). o.intent is
  the stored canonical user-row target, whose modelSelection/mode/planEnabled
  were frozen at the original send time. Downstream resolves each with a
  `?? current` fallback (e.g. kPo: modelSelection ?? getSessionModelSelection();
  runtimeConfig: mode ?? sessionMode ?? config.permission.mode), so a present
  (stale) value wins and the new settings never take over. Dropping the three
  fields makes each fall back to the current session value.

Patch: replace "modelSelection:o.intent.modelSelection,mode:o.intent.mode,
planEnabled:o.intent.planEnabled," with an idempotency comment marker inside
SJo's kJo(...) object literal. Valid because JS object literals allow
comments between properties.

Idempotency marker: zcode-editresend-model-fix
File is handled as raw bytes end-to-end so line endings are preserved exactly.
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
    """Best-effort syntax validation; skipped when node is unavailable."""
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
    ap = argparse.ArgumentParser(description=f"{SLUG}: inject stale-settings fix")
    ap.add_argument("--dir", default=None, help=argparse.SUPPRESS)  # accepted, unused
    ap.add_argument("--zcode-cjs", default=None, help="path to resources/glm/zcode.cjs")
    ap.add_argument("--install-root", default=None, help=argparse.SUPPRESS)  # accepted, unused
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

    n = data.count(OLD)
    if n != 1:
        fail(f"anchor matched {n} times (expected 1); refusing to inject (version drift?)", 2)

    new_data = data.replace(OLD, NEW, 1)

    if not node_check(new_data):
        fail("syntax check failed; nothing written", 3)
    if MARKER not in new_data or new_data.count(OLD) != 0:
        fail("post-inject content check failed; nothing written", 4)

    tpath.write_bytes(new_data)
    log("injected: removed stale modelSelection/mode/planEnabled from SJo re-run")


if __name__ == "__main__":
    main()
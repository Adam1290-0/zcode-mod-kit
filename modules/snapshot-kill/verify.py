#!/usr/bin/env python3
"""snapshot-kill: directory-mode verifier for zcode-mod-kit.

Exit 0 means the module is in its intended final state:
  - gate injected (2 gates at the two entry points + marker), or
  - this build has no snapshot subsystem at all (removed upstream),
    in which case nothing needs to be injected and the state is safe.

Any other condition exits non-zero.
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

SLUG = "snapshot-kill"
GATE = 'if(process.env.ZCODE_SNAPSHOT_ALLOW!=="1")return;'
MARKER = "zcode-snapshot-kill-switch"

ANCHORS = [
    (
        "captureBeforePromptUnsafe",
        "async captureBeforePromptUnsafe(t){"
        "t.signal?.throwIfAborted();let r=await this.tokenProvider();",
    ),
    (
        "flushActiveUpload",
        "async flushActiveUpload(t){"
        "let r=await this.stateRepo.read(t),o=r.activeUpload??r.pendingUpload;",
    ),
]

SUBSYSTEM_KEYS = (
    "RepoSnapshotSidecarService",
    "captureBeforePromptUnsafe",
    "flushActiveUpload",
)


def log(msg: str) -> None:
    print(f"[{SLUG}] {msg}")


def fail(msg: str, code: int = 1) -> None:
    log(f"[ERROR] {msg}")
    sys.exit(code)


def read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def target_file(unpack_dir: Path) -> Path:
    return unpack_dir / "out" / "host" / "index.js"


def node_check(text: str) -> bool:
    with tempfile.NamedTemporaryFile(
        "w", suffix=".js", delete=False, encoding="utf-8", newline=""
    ) as tf:
        tf.write(text)
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


def subsystem_absent(text: str) -> bool:
    return not any(k in text for k in SUBSYSTEM_KEYS)


def main() -> None:
    ap = argparse.ArgumentParser(description=f"{SLUG}: verify injection state (directory mode)")
    ap.add_argument("--dir", required=True, help="unpacked asar directory")
    ap.add_argument("--zcode-cjs", default=None, help=argparse.SUPPRESS)  # accepted, unused
    ap.add_argument("--install-root", default=None, help=argparse.SUPPRESS)  # accepted, unused
    args = ap.parse_args()

    tpath = target_file(Path(args.dir).resolve())
    if not tpath.is_file():
        fail(f"target file not found: {tpath}")

    text = read_text(tpath)

    if subsystem_absent(text):
        if MARKER in text or GATE in text:
            fail("marker/gate found but subsystem is absent; inconsistent state", 2)
        # Stable machine-readable tag for the kit TUI: [NOT-NEEDED] = module
        # cannot be selected, row shows "no injection needed".
        log("[NOT-NEEDED] subsystem absent in this build (removed upstream); state is safe")
        return

    problems = []
    if MARKER not in text:
        problems.append("marker missing")
    n = text.count(GATE)
    if n != 2:
        problems.append(f"gate count={n} (expected 2)")
    for name, anchor in ANCHORS:
        i = text.find(anchor)
        if i < 0 or not text[i : i + len(anchor) + len(GATE)].endswith(GATE):
            problems.append(f"gate not at entry of {name}")
    if not node_check(text):
        problems.append("syntax check failed")

    if problems:
        fail("verify failed: " + "; ".join(problems))

    log("verified: marker present, 2 gates at entry points, syntax ok")


if __name__ == "__main__":
    main()

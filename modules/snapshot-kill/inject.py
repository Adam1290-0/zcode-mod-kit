#!/usr/bin/env python3
"""snapshot-kill: directory-mode injector for zcode-mod-kit.

Injects a default-deny gate into the repo-snapshot subsystem entry points
inside <dir>/out/host/index.js (the unpacked asar tree managed by the kit).

Gate semantics (frozen):
  if(process.env.ZCODE_SNAPSHOT_ALLOW!=="1")return;
  -> snapshot capture/upload blocked by default;
     setting ZCODE_SNAPSHOT_ALLOW=1 restores official behavior.

Idempotency marker: zcode-snapshot-kill-switch
If the target build no longer contains the subsystem (removed upstream),
the script reports it and exits 0 without touching the file.

Files are handled as raw bytes end-to-end so line endings (\r\n/\n) are
preserved exactly, which keeps uninject byte-identical restoration possible.
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

SLUG = "snapshot-kill"
GATE = 'if(process.env.ZCODE_SNAPSHOT_ALLOW!=="1")return;'
MARKER = "\n/*[zcode-snapshot-kill-switch]*/const ZCODE_REPO_SNAPSHOT_KILL_MARK=1;"

# Entry-point anchors inside out/host/index.js (each must be unique per file).
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

# Anchor used to place the idempotency marker declaration.
MARKER_POS = (
    'a(pIe,"removeGeneratedArtifactFiles");'
    'var Bk=class{static{a(this,"RepoSnapshotSidecarService")}'
)

# If none of these appear, the build has no snapshot subsystem at all.
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
    # bytes round-trip keeps line endings untouched
    return path.read_bytes().decode("utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_bytes(text.encode("utf-8"))


def target_file(unpack_dir: Path) -> Path:
    return unpack_dir / "out" / "host" / "index.js"


def node_check(text: str) -> bool:
    """Best-effort syntax validation; skipped when node is unavailable."""
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
    ap = argparse.ArgumentParser(description=f"{SLUG}: inject snapshot gate (directory mode)")
    ap.add_argument("--dir", required=True, help="unpacked asar directory")
    ap.add_argument("--zcode-cjs", default=None, help=argparse.SUPPRESS)  # accepted, unused
    ap.add_argument("--install-root", default=None, help=argparse.SUPPRESS)  # accepted, unused
    args = ap.parse_args()

    tpath = target_file(Path(args.dir).resolve())
    if not tpath.is_file():
        fail(f"target file not found: {tpath}")
    log(f"target: {tpath}")

    text = read_text(tpath)

    if "zcode-snapshot-kill-switch" in text:
        log("[SKIP] already injected")
        return

    if subsystem_absent(text):
        # Stable machine-readable tag for the kit TUI: [NOT-NEEDED] = module
        # cannot be selected, row shows "no injection needed".
        log("[NOT-NEEDED] repo-snapshot subsystem absent in this build (removed upstream); nothing to inject")
        return

    for name, anchor in ANCHORS:
        n = text.count(anchor)
        if n != 1:
            fail(f"anchor {name} matched {n} times (expected 1); refusing to inject", 2)
        log(f"anchor ok: {name}")

    mpos = text.count(MARKER_POS)
    if mpos != 1:
        fail(f"marker anchor matched {mpos} times (expected 1)", 2)

    for _, anchor in ANCHORS:
        idx = text.index(anchor) + len(anchor)
        text = text[:idx] + GATE + text[idx:]

    m = text.index(MARKER_POS)
    text = text[:m] + MARKER + text[m:]

    if not node_check(text):
        fail("syntax check failed; nothing written", 3)
    if "zcode-snapshot-kill-switch" not in text or text.count(GATE) != 2:
        fail("post-inject content check failed; nothing written", 4)

    write_text(tpath, text)
    log(f"injected: 2 gates + marker ({tpath})")


if __name__ == "__main__":
    main()

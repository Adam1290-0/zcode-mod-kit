#!/usr/bin/env python3
"""snapshot-kill: directory-mode uninjector for zcode-mod-kit.

Removes exactly what inject.py added into <dir>/out/host/index.js:
  - the default-deny gate (2 occurrences, contains ZCODE_SNAPSHOT_ALLOW)
  - the idempotency marker block (zcode-snapshot-kill-switch)

No other content is touched, so a file that only this module injected is
restored byte-identically. Never injected / nothing to remove -> exit 0.
"""
import argparse
import sys
from pathlib import Path

SLUG = "snapshot-kill"
GATE = 'if(process.env.ZCODE_SNAPSHOT_ALLOW!=="1")return;'
MARKER = "\n/*[zcode-snapshot-kill-switch]*/const ZCODE_REPO_SNAPSHOT_KILL_MARK=1;"

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


def write_text(path: Path, text: str) -> None:
    path.write_bytes(text.encode("utf-8"))


def target_file(unpack_dir: Path) -> Path:
    return unpack_dir / "out" / "host" / "index.js"


def subsystem_absent(text: str) -> bool:
    return not any(k in text for k in SUBSYSTEM_KEYS)


def main() -> None:
    ap = argparse.ArgumentParser(description=f"{SLUG}: remove snapshot gate (directory mode)")
    ap.add_argument("--dir", required=True, help="unpacked asar directory")
    ap.add_argument("--zcode-cjs", default=None, help=argparse.SUPPRESS)  # accepted, unused
    ap.add_argument("--install-root", default=None, help=argparse.SUPPRESS)  # accepted, unused
    args = ap.parse_args()

    tpath = target_file(Path(args.dir).resolve())
    if not tpath.is_file():
        fail(f"target file not found: {tpath}")
    log(f"target: {tpath}")

    original = read_text(tpath)
    text = original
    changed = False

    # Remove the marker block first (single, well-delimited insertion).
    if MARKER in text:
        text = text.replace(MARKER, "", 1)
        changed = True

    # Remove gates. The gate string embeds ZCODE_SNAPSHOT_ALLOW, which only
    # this module injects, so removing every occurrence is scope-safe.
    gate_count = text.count(GATE)
    if gate_count:
        text = text.replace(GATE, "")
        changed = True

    if not changed:
        if subsystem_absent(original):
            log("[NOT-NEEDED] subsystem absent in this build; nothing to remove")
        else:
            log("[SKIP] not injected")
        return

    residue = []
    if MARKER in text:
        residue.append("marker")
    if text.count(GATE) != 0:
        residue.append(f"gate x{text.count(GATE)}")
    if residue:
        fail(f"unexpected residue after removal: {', '.join(residue)}", 2)

    write_text(tpath, text)
    log(f"removed: marker + {gate_count} gate(s) from {tpath}")


if __name__ == "__main__":
    main()

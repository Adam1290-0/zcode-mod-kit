#!/usr/bin/env python3
"""zombie-cleanup: zcode-cjs verifier for zcode-mod-kit.

Exit 0 means the marker is present (injected). Any other state exits non-zero.
"""
import argparse
import os
import sys
from pathlib import Path

SLUG = "zombie-cleanup"
MARKER = b"zcode-zombie-cleanup"
RUNTIME_DIR = Path(os.path.expanduser("~/.zcode/plugins/zombie-cleanup"))
CLEANUP_SCRIPT_NAME = "cleanup_mcp_zombies.ps1"
TASK_INSTALLER_NAME = "install-scheduled-task.ps1"
# Every file inject.py copies into the runtime dir. The skip gate trusts this
# verifier, so anything written but not checked here would stay at an old
# version forever - the blind spot that already shipped a stale skin block and
# a stale voice sidecar.
DEPLOYED_ASSETS = (CLEANUP_SCRIPT_NAME, TASK_INSTALLER_NAME)
CLEANUP_SCRIPT = str((RUNTIME_DIR / CLEANUP_SCRIPT_NAME).as_posix())
# Pre-kit manual patch (scripts/patch_zcode_mcp_cleanup.py) injected the same
# payload without the marker. Functionally identical -> count as injected.
LEGACY_CORE = (
    b'require("child_process").spawn("powershell",'
    b'["-NoProfile","-ExecutionPolicy","Bypass","-WindowStyle","Hidden",'
    b'"-File","' + CLEANUP_SCRIPT.encode() + b'"'
)


def main() -> None:
    ap = argparse.ArgumentParser(description=f"{SLUG}: verifier")
    ap.add_argument("--dir", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--zcode-cjs", default=None, help="path to resources/glm/zcode.cjs")
    ap.add_argument("--install-root", default=None, help=argparse.SUPPRESS)
    args = ap.parse_args()
    if not args.zcode_cjs:
        print(f"[{SLUG}] FAIL: missing --zcode-cjs path")
        sys.exit(1)
    tpath = Path(args.zcode_cjs).resolve()
    if not tpath.is_file():
        print(f"[{SLUG}] FAIL: target file not found: {tpath}")
        sys.exit(1)
    data = tpath.read_bytes()
    if MARKER not in data and LEGACY_CORE not in data:
        print(f"[{SLUG}] FAIL: cleanup trigger not found")
        sys.exit(1)
    # The injected powershell call resolves at runtime from RUNTIME_DIR, so an
    # absent script means the module is injected but functionally dead (the
    # spawn fails silently). Treat it as a failure so the installer redeploys.
    # Existence is not enough either: an updated script would never be
    # re-deployed, because the skip gate trusts this verifier and a stale copy
    # still reads as "injected". Compare every deployed asset byte-for-byte.
    asset_dir = Path(__file__).resolve().parent / "assets"
    if not asset_dir.is_dir():
        asset_dir = Path(__file__).resolve().parent
    stale = []
    for name in DEPLOYED_ASSETS:
        deployed = RUNTIME_DIR / name
        if not deployed.is_file():
            print(f"[{SLUG}] FAIL: {name} missing at {deployed}")
            sys.exit(1)
        src = asset_dir / name
        if src.is_file() and deployed.read_bytes() != src.read_bytes():
            stale.append(name)
    if stale:
        # 2, not 1: the module IS injected, the installed files are just old.
        # Returning 1 made uninstall treat it as absent and skip the removal.
        print(f"[{SLUG}] STALE: deployed asset(s) differ from the module: "
              f"{', '.join(stale)}")
        sys.exit(2)
    print(f"[{SLUG}] verified: cleanup trigger injected + "
          f"{len(DEPLOYED_ASSETS)} runtime asset(s) current")
    return 0


if __name__ == "__main__":
    sys.exit(main())
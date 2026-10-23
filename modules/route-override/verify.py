#!/usr/bin/env python3
"""route-override module — injection state verifier.

Usage:
  python verify.py --dir <extracted_asar_dir> [--zcode-cjs <path>]

Exit 0 = fully injected and complete; exit 1 = missing/incomplete.
Checks:
  - zcode.cjs: /*zro*/ marker unique and within the first 500 bytes
  - renderer:  marker block exists with token + findEditPanel + upsert +
               MutationObserver feature markers
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inject import verify, RUNTIME_DIR  # noqa: E402


def runtime_is_current() -> bool:
    """The deployed wrapper must byte-match this module's asset.

    asar/zcode.cjs markers say nothing about ~/.zcode/plugins/<slug>/, and the
    kit's outer SKIP gate decides from this verifier alone. Without this check
    a re-install silently keeps an OLD runtime wrapper forever - exactly the
    2026-09-28 class ("fixed in repo, never reached the machine"), which this
    time hid a port-retry listener leak for a month.
    """
    asset = Path(__file__).resolve().parent / "assets" / "wrapper.js"
    deployed = RUNTIME_DIR / "wrapper.js"
    if not deployed.exists():
        print("[route-override] verify: deployed wrapper missing ->", deployed)
        return False
    if deployed.read_bytes() != asset.read_bytes():
        print("[route-override] verify: deployed wrapper is STALE (differs from asset)")
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="route-override injection verifier")
    ap.add_argument("--dir", required=True, help="extracted asar out directory")
    ap.add_argument("--zcode-cjs", default=None, help="path to resources/glm/zcode.cjs")
    args = ap.parse_args()

    out_dir = Path(args.dir)
    if not out_dir.exists():
        print("[route-override] [ERROR] --dir not found:", out_dir)
        return 1
    rc = verify(out_dir, Path(args.zcode_cjs) if args.zcode_cjs else None)
    fresh = runtime_is_current()
    if rc == 0 and not fresh:
        print("[route-override] verify: FAIL (runtime wrapper stale)")
        return 1
    return rc


if __name__ == "__main__":
    sys.exit(main())

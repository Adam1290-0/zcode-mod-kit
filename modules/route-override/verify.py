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
from inject import verify  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="route-override injection verifier")
    ap.add_argument("--dir", required=True, help="extracted asar out directory")
    ap.add_argument("--zcode-cjs", default=None, help="path to resources/glm/zcode.cjs")
    args = ap.parse_args()

    out_dir = Path(args.dir)
    if not out_dir.exists():
        print("[route-override] [ERROR] --dir not found:", out_dir)
        return 1
    return verify(out_dir, Path(args.zcode_cjs) if args.zcode_cjs else None)


if __name__ == "__main__":
    sys.exit(main())

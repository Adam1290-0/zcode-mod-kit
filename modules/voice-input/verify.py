#!/usr/bin/env python3
"""voice-input module — standalone verifier for the ZCode Mod Kit (v0.2).

Usage:
  python verify.py --dir <extracted-asar-root>

Exit 0 = all checks pass (renderer + main process + runtime files).
"""
import sys, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inject import verify


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--install-root", default=None)
    args = ap.parse_args()
    return verify(Path(args.dir))


if __name__ == "__main__":
    sys.exit(main())

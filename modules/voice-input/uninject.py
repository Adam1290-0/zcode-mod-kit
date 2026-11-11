#!/usr/bin/env python3
"""voice-input module — uninjector for the ZCode Mod Kit (v0.2).

Removes both injection points (renderer script block + out/main/index.js
import line). Runtime dir survives unless --purge-runtime, so a re-inject
keeps the same token, config, deps and models.

Usage:
  python uninject.py --dir <extracted-asar-root> [--purge-runtime]
"""
import sys, argparse, shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inject import RUNTIME_DIR, uninject_renderer, uninject_main, log


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="extracted asar root")
    ap.add_argument("--install-root", default=None)
    ap.add_argument("--purge-runtime", action="store_true",
                    help="also delete the runtime dir (deps/models/config/token)")
    args = ap.parse_args()

    out_dir = Path(args.dir)
    uninject_renderer(out_dir)
    uninject_main(out_dir)

    if args.purge_runtime and RUNTIME_DIR.exists():
        shutil.rmtree(RUNTIME_DIR)
        log(f"purged runtime dir {RUNTIME_DIR}")
    else:
        log(f"runtime dir kept (use --purge-runtime to remove): {RUNTIME_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

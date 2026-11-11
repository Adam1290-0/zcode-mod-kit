#!/usr/bin/env python3
"""usage-stats-fallback: zcode-cjs uninjector for zcode-mod-kit.

Restores the original Xkr function by removing both insertion blocks.
"""
import argparse
import sys
from pathlib import Path

SLUG = "usage-stats-fallback"
# ANCHOR1's minified variable name rotates between releases (R on 3.17.2,
# P on 3.18.0, ...). inject.py discovers it with a regex, so uninject must NOT
# hardcode one spelling - doing so left the block in place on every release
# whose name differed (observed on 3.18.0: markers still present after
# uninject). Removal is therefore marker-bounded: each insert starts at its
# own /*zusage-fb-*\/ marker and ends at the literal tail below.
ANCHOR2 = b"return{totals:{"
MARKER1 = b"zusage-fb-day"
MARKER2 = b"zusage-fb-merge"
# The insert is ONE contiguous 1209-byte span that WRAPS the upstream
# model_usage query (verified by common-prefix/suffix alignment against a real
# injection on 3.18.0). Its shape:
#   ;/*zusage-fb-day*/ <day-fallback> }} [upstream query: let <X>=e.prepare(...)...all(i,a,n,o);]
#   ;/*zusage-fb-merge*/ <merge> modelRequestCount??0     <- then upstream: )||0 ... hmm
# Cutting exactly this span is not expressible with markers alone (the upstream
# query sits inside), so removal is done in two marker-bounded pieces:
#   piece A: ';/*zusage-fb-day*/' .. the 'let ' that starts the upstream query
#   piece B: ';;/*zusage-fb-merge*/' .. the end of the injected merge expression
# Both bounds are literals from the real bundle, not minified names.
PREFIX_A = b";/*zusage-fb-day*/"
TAIL_A = b"}}let "                       # block A ends here; 'let ' is upstream
PREFIX_B = b";;/*zusage-fb-merge*/"
TAIL_B = b"c.modelRequestCount=Number(c.modelRequestCount??0)"

def _cut_blocks(data: bytes) -> bytes:
    """Remove both inserted pieces, keeping the upstream query between them.

    Piece A sits before the upstream model_usage query, piece B after it (see
    the constants above). Each is cut from its literal prefix to its literal
    tail; neither bound contains a minified variable name, which rotate every
    release.
    """
    a = data.find(PREFIX_A)
    if a >= 0:
        t = data.find(TAIL_A, a)
        if t >= 0:
            # keep the trailing `let ` (upstream query start)
            data = data[:a] + data[t + len(TAIL_A) - len(b"let "):]
    b = data.find(PREFIX_B)
    if b >= 0:
        t2 = data.find(TAIL_B, b)
        if t2 >= 0:
            data = data[:b] + data[t2 + len(TAIL_B):]
    return data


def main() -> None:
    ap = argparse.ArgumentParser(description=f"{SLUG}: uninjector")
    ap.add_argument("--dir", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--zcode-cjs", default=None, help="path to resources/glm/zcode.cjs")
    ap.add_argument("--install-root", default=None, help=argparse.SUPPRESS)
    args = ap.parse_args()
    if not args.zcode_cjs:
        print(f"[{SLUG}] missing --zcode-cjs path")
        sys.exit(1)
    tpath = Path(args.zcode_cjs).resolve()
    if not tpath.is_file():
        print(f"[{SLUG}] target file not found: {tpath}")
        sys.exit(1)
    data = tpath.read_bytes()
    if MARKER1 not in data and MARKER2 not in data:
        print(f"[{SLUG}] [SKIP] not injected")
        return
    # Cut from the LATER block backwards is no longer needed: both blocks sit in
    # one contiguous span, so a single cut removes them (see _cut_blocks).
    new = _cut_blocks(data)
    if MARKER1 in new or MARKER2 in new:
        print(f"[{SLUG}] [ERROR] markers still present after uninject")
        sys.exit(1)
    tpath.write_bytes(new)
    print(f"[{SLUG}] restored: usage fallback removed from Xkr")


if __name__ == "__main__":
    main()
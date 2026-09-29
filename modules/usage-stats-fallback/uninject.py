#!/usr/bin/env python3
"""usage-stats-fallback: zcode-cjs uninjector for zcode-mod-kit.

Restores the original Xkr function by removing both insertion blocks.
"""
import argparse
import sys
from pathlib import Path

SLUG = "usage-stats-fallback"
ANCHOR1 = b"let R=e.prepare("
ANCHOR2 = b"return{totals:{"
MARKER1 = b"zusage-fb-day"
MARKER2 = b"zusage-fb-merge"

# The injected form is: INSERT1 + ANCHOR1 and INSERT2 + ANCHOR2
# We must reconstruct the exact insert to remove it.
INSERT1 = (
    b";/*zusage-fb-day*/"
    b"let zz=n;if(zz<Date.parse('2026-09-01')){"
    b"let qq=e.prepare('select cast((time_created+?)/? as integer) as dayIndex,"
    b"coalesce(sum(cast(json_extract(data,\\'$.tokens.input\\') as integer)+"
    b"cast(json_extract(data,\\'$.tokens.output\\') as integer)),0) as totalTokens "
    b"from message where time_created>=? and time_created<? "
    b"and json_extract(data,\\'$.semantics.kind\\')=\\'assistant_response\\' "
    b"and json_extract(data,\\'$.tokens\\') is not null group by dayIndex')"
    b".all(s,a,n,o);"
    b"for(let L of qq){let U=E.get(L.dayIndex);"
    b"U||(U={dayIndex:L.dayIndex,totalTokens:0,turnCount:0,toolCallCount:0},"
    b"E.set(L.dayIndex,U));U.totalTokens+=Number(L.totalTokens)}}"
)
INSERT2 = (
    b";/*zusage-fb-merge*/"
    b"let mt=0,mi=0;for(let L of E.values()){mt+=L.totalTokens;mi+=L.turnCount}"
    b";l.totalTokens=(Number(l.totalTokens??0)+mt)||0"
    b";l.modelRequestCount=Number(l.modelRequestCount??0);"
)


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
    new = data.replace(INSERT1 + ANCHOR1, ANCHOR1, 1)
    new = new.replace(INSERT2 + ANCHOR2, ANCHOR2, 1)
    if MARKER1 in new or MARKER2 in new:
        print(f"[{SLUG}] [ERROR] markers still present after uninject")
        sys.exit(1)
    tpath.write_bytes(new)
    print(f"[{SLUG}] restored: usage fallback removed from Xkr")


if __name__ == "__main__":
    main()
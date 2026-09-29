#!/usr/bin/env python3
"""usage-stats-fallback: zcode-cjs injector for zcode-mod-kit.

Backfills the official usage-stats page (settings -> usage) by adding a
message-table fallback inside Xkr(queryAppUsage) in zcode.cjs.

Root cause: ZCode switched token-usage storage from message.data.tokens
(JSON, pre 2026-09-01) to the model_usage table (post 2026-09-01). The
official stats page only queries model_usage, so all pre-September data
appears to be "zero". The CLI zusage.py already has a similar fallback
(via _message_range_usage); this module brings it to the GUI.

Two insertions in async function Xkr(e,t):
  1. After the daily-aggregation loop (E Map) and before the model-by-day
     query (let R=e.prepare): if the window starts before model_usage's
     first known record, query message.data.tokens per-day totals and
     merge them into E.  Marker: /*zusage-fb-day*/
  2. Before the return statement: recompute totals/models from the
     augmented E/dayModels so the summary and model-ranking reflect
     both old and new data.  Marker: /*zusage-fb-merge*/

Both anchors are byte-unique inside the Xkr function body (verified on
3.14.4). The patch is idempotent: markers already present -> SKIP.
All operations are raw-byte to preserve line endings.
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

SLUG = "usage-stats-fallback"
ANCHOR1 = b"let R=e.prepare("
ANCHOR2 = b"return{totals:{"
MARKER1 = b"zusage-fb-day"
MARKER2 = b"zusage-fb-merge"

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

def log(msg: str) -> None:
    print(f"[{SLUG}] {msg}")

def fail(msg: str, code: int = 1) -> None:
    log(f"[ERROR] {msg}")
    sys.exit(code)

def node_check(data: bytes) -> bool:
    """Best-effort syntax validation; skipped when node is unavailable."""
    with tempfile.NamedTemporaryFile("wb", suffix=".js", delete=False) as tf:
        tf.write(data)
        path = tf.name
    try:
        proc = subprocess.run(["node", "--check", path], capture_output=True,
                              text=True, timeout=120)
        if proc.returncode != 0:
            log(f"node --check failed: {proc.stderr[:500]}")
            return False
        return True
    except FileNotFoundError:
        log("node not found, skipping syntax check")
        return True
    finally:
        Path(path).unlink(missing_ok=True)

def main() -> None:
    ap = argparse.ArgumentParser(description=f"{SLUG}: inject usage fallback")
    ap.add_argument("--dir", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--zcode-cjs", default=None,
                    help="path to resources/glm/zcode.cjs")
    ap.add_argument("--install-root", default=None, help=argparse.SUPPRESS)
    args = ap.parse_args()
    if not args.zcode_cjs:
        fail("missing --zcode-cjs path")
    tpath = Path(args.zcode_cjs).resolve()
    if not tpath.is_file():
        fail(f"target file not found: {tpath}")
    log(f"target: {tpath}")
    data = tpath.read_bytes()

    if MARKER1 in data and MARKER2 in data:
        log("[SKIP] already injected")
        return

    # --- anchor1: day-level fallback before let R=e.prepare( ---
    if data.count(ANCHOR1) != 1:
        fail(f"anchor1 matched {data.count(ANCHOR1)} times (expected 1); "
             f"refusing to inject (version drift?)", 2)
    # --- anchor2: totals merge before return{totals:{ ---
    if data.count(ANCHOR2) != 1:
        fail(f"anchor2 matched {data.count(ANCHOR2)} times (expected 1); "
             f"refusing to inject (version drift?)", 2)

    new = data.replace(ANCHOR1, INSERT1 + ANCHOR1, 1)
    new = new.replace(ANCHOR2, INSERT2 + ANCHOR2, 1)

    if not node_check(new):
        fail("syntax check failed; nothing written", 3)
    if MARKER1 not in new or MARKER2 not in new:
        fail("post-inject marker check failed; nothing written", 4)

    tpath.write_bytes(new)
    log("injected: message.data.tokens fallback added to Xkr(queryAppUsage)")


if __name__ == "__main__":
    main()
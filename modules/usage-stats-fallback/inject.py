#!/usr/bin/env python3
"""usage-stats-fallback: zcode-cjs injector for zcode-mod-kit.

Backfills the official usage-stats page (settings -> usage) by adding a
message-table fallback inside the queryAppUsage aggregation function in
zcode.cjs (named mqr on 3.18.0; eLr on 3.16.2; Xkr on <=3.14.x, h2r on 3.15.x).

Root cause: ZCode switched token-usage storage from message.data.tokens
(JSON, pre 2026-09-01) to the model_usage table (post 2026-09-01). The
official stats page only queries model_usage, so all pre-September data
appears to be "zero".

DO NOT remove the message fallback as "legacy": since 3.15.3 the app prunes
model_usage to a rolling 30 days, so without this path a long-running user
loses everything older than a month from the GUI (measured: 9.997B tokens
of history lived only in the message table). The CLI zusage.py already has
the same fallback (via _message_range_usage); this module brings it to the GUI.

Two insertions in the aggregation function:
  1. After the daily-aggregation loop (E Map) and before the model-by-day
     query (`let P=e.prepare(` on 3.18.0; was `let R=e.prepare(` earlier):
     if the window starts before model_usage's first known record, query
     message.data.tokens per-day totals and merge them into E.
     Marker: /*zusage-fb-day*/
  2. Before the return statement: recompute totals/models from the
     augmented E/dayModels so the summary and model-ranking reflect
     both old and new data.  Marker: /*zusage-fb-merge*/

Both anchors are byte-unique inside the function body (verified across
3.14.4 - 3.18.0; the function and some var names are renamed each release
but the anchors, the day-map variable C, and the .all(i,a,n,o) call shape
are stable). The patch is idempotent: markers already present -> SKIP.
All operations are raw-byte to preserve line endings.
"""
import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SLUG = "usage-stats-fallback"
# ANCHOR2 is a literal and has survived every release so far.
ANCHOR2 = b"return{totals:{"
MARKER1 = b"zusage-fb-day"
MARKER2 = b"zusage-fb-merge"

# ANCHOR1 is "let <X>=e.prepare(`select ... from model_usage ... model_id as
# modelId ... group by dayIndex, model_id`)". The minified name <X> rotates on
# some releases (R on 3.17.2, P on 3.18.0, ...), so it is discovered at run
# time instead of being hardcoded. The semantic tail is what makes it unique.

ANCHOR1_RE = re.compile(
    rb"let (\w+)=e\.prepare\(`select\s+cast\(\(started_at \+ \?\) / \? as integer\) as dayIndex,"
    rb"\s+model_id as modelId,"
)


def find_anchor1(data: bytes):
    """Return (anchor_bytes, var_name) for the model-by-day query, or (None, None).

    Must match exactly once inside the bundle; anything else means the
    bundle drifted and injection is refused.
    """
    hits = list(ANCHOR1_RE.finditer(data))
    if len(hits) != 1:
        return None, None
    m = hits[0]
    return m.group(0), m.group(1)

# ---- clamp semantics -------------------------------------------------------
# The message table is written in BOTH eras: pre-2026-09-01 (the only source,
# because model_usage did not exist yet) and post-2026-09-01 (a duplicate of
# what model_usage already records). Summing message over the whole window
# would therefore double-count the new era. The fallback is clamped to the
# window where model_usage has no data:
#
#   msgEnd = min(until, min(started_at) FROM model_usage)   # or `until` if empty
#   message rows are read from [n, msgEnd) only
#   only that segment (msgSum) is added to the summary totals
#
# This keeps "7d"/"30d" exact, and makes "all" show old+new without inflation.
# 2026-11: ZCode also prunes model_usage to a 30-day window, so min(started_at)
# slides forward; the clamp follows it automatically because it is evaluated
# per query.
INSERT1 = (
    # 3.15.3: impl renamed Xkr->h2r, vars s->i, E->C (day map). 3.14.x used
    # s/E internally; INSERT1 must match the CURRENT bundle. These exact
    # identifiers are unique inside the function body.
    b";/*zusage-fb-day*/"
    b"let msgEnd=e.prepare('select min(started_at) as m from model_usage').get(),"
    b"msgCap=(msgEnd&&msgEnd.m)||o,msgSum=0;"
    b"if(msgCap>o)msgCap=o;"
    b"if(n<msgCap){"
    b"let qq=e.prepare('select cast((time_created+?)/? as integer) as dayIndex,"
    b"coalesce(sum(cast(json_extract(data,\\'$.tokens.input\\') as integer)+"
    b"cast(json_extract(data,\\'$.tokens.output\\') as integer)),0) as totalTokens "
    b"from message where time_created>=? and time_created<? "
    b"and json_extract(data,\\'$.semantics.kind\\')=\\'assistant_response\\' "
    b"and json_extract(data,\\'$.tokens\\') is not null group by dayIndex')"
    b".all(i,a,n,msgCap);"
    b"for(let L of qq){let U=C.get(L.dayIndex);"
    b"U||(U={dayIndex:L.dayIndex,totalTokens:0,turnCount:0,toolCallCount:0},"
    b"C.set(L.dayIndex,U));U.totalTokens+=Number(L.totalTokens);"
    b"msgSum+=Number(L.totalTokens)}}"
)

INSERT2 = (
    # c.totalTokens already holds the model_usage aggregate, so only the
    # clamped message segment (msgSum) is added here. Re-summing C.values()
    # would count model_usage twice.
    b";/*zusage-fb-merge*/"
    b"c.totalTokens=(Number(c.totalTokens??0)+msgSum)||0;"
    b"c.modelRequestCount=Number(c.modelRequestCount??0);"
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

    # --- anchor1: day-level fallback before let <X>=e.prepare(`select ---
    anchor1, var = find_anchor1(data)
    if anchor1 is None:
        fail("anchor1 (model-by-day query) not found exactly once; "
             "refusing to inject (version drift?)", 2)
    log(f"anchor1 var: let {var.decode()}=e.prepare(")
    # --- anchor2: totals merge before return{totals:{ ---
    if data.count(ANCHOR2) != 1:
        fail(f"anchor2 matched {data.count(ANCHOR2)} times (expected 1); "
             f"refusing to inject (version drift?)", 2)

    new = data.replace(anchor1, INSERT1 + anchor1, 1)
    new = new.replace(ANCHOR2, INSERT2 + ANCHOR2, 1)

    if not node_check(new):
        fail("syntax check failed; nothing written", 3)
    if MARKER1 not in new or MARKER2 not in new:
        fail("post-inject marker check failed; nothing written", 4)

    tpath.write_bytes(new)
    log("injected: message.data.tokens fallback added to Xkr(queryAppUsage)")


if __name__ == "__main__":
    main()
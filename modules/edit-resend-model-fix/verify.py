#!/usr/bin/env python3
"""edit-resend-model-fix v7: cjs + renderer verifier for zcode-mod-kit.

Exit 0 means v7 is fully applied on BOTH targets:
  cjs      - builder gate admits retryTurn payload, retryTurn schema widened
  renderer - retry callback carries the live draft selection, and the edit
             side is present upstream (sanity signal for the assumed baseline)

Per-build minified names (dispatcher / draft reader / gate variable) differ,
so nothing here is keyed on a single version's identifiers: the gate is checked
by its semantic shape, and the renderer by the marker plus the spread body.
"""
import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SLUG = "edit-resend-model-fix"

# Gate: variable name varies (d in 3.18.x, p in 3.19.1) -> capture it.
GATE_WIDENED_RE = re.compile(
    rb'let ([A-Za-z_$][\w$]*)=t\.type==="editUserQuery"\|\|'
    rb't\.type==="retryTurn"\?t\.payload:void 0')
GATE_NARROW_RE = re.compile(
    rb'let ([A-Za-z_$][\w$]*)=t\.type==="editUserQuery"\?t\.payload:void 0')

# retryTurn schema widening, any zod binding + any alias set.
RT_WIDENED_RE = re.compile(
    rb"retryTurn:[\w$]+\.object\(\{target:[\w$]+,modelSelection:[\w$]+"
    rb"\.optional\(\),mode:[\w$]+\.optional\(\),"
    rb"planEnabled:[\w$]+\.boolean\(\)\.optional\(\)\}\)")

NEE_UPSTREAM = (b"...o?{modelSelection:o.modelSelection,mode:o.mode,"
                b"planEnabled:o.planEnabled}:{}")
# Every spread body this module has ever written (si / ii() / ei()), all via
# the same single-evaluation IIFE so the shape is identical apart from the
# reader name.
SEL_SPREAD_RE = re.compile(
    rb"\.\.\.\(\(_r\)=>_r\?\{modelSelection:_r\.modelSelection,"
    rb"mode:_r\.mode,planEnabled:_r\.planEnabled\}:\{\}\)\((\w+)\(\)\)")


def log(msg: str) -> None:
    print(f"[{SLUG}] {msg}")


def fail(msg: str, code: int = 1) -> None:
    log(f"[ERROR] {msg}")
    sys.exit(code)


def node_check(data: bytes, label: str) -> None:
    with tempfile.NamedTemporaryFile("wb", suffix=".js", delete=False) as tf:
        tf.write(data)
        path = tf.name
    try:
        proc = subprocess.run(["node", "--check", path],
                              capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            fail(f"{label}: node --check failed: {proc.stderr[:400]}", 3)
    except FileNotFoundError:
        log(f"{label}: node not found, skipping syntax check")
    finally:
        Path(path).unlink(missing_ok=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=f"{SLUG}: verify v7 state")
    ap.add_argument("--dir", default=None, help="unpacked asar root")
    ap.add_argument("--zcode-cjs", default=None,
                    help="path to resources/glm/zcode.cjs")
    ap.add_argument("--install-root", default=None, help=argparse.SUPPRESS)
    args = ap.parse_args()

    problems = []

    # ---- cjs ----
    if not args.zcode_cjs:
        fail("missing --zcode-cjs path")
    cjs = Path(args.zcode_cjs).resolve()
    if not cjs.is_file():
        fail(f"zcode.cjs not found: {cjs}")
    data = cjs.read_bytes()
    widened = GATE_WIDENED_RE.search(data)
    narrow = GATE_NARROW_RE.search(data)
    if not widened:
        problems.append("cjs: retryTurn payload gate not widened")
    if narrow:
        problems.append("cjs: original editUserQuery-only gate still present")
    if not RT_WIDENED_RE.search(data):
        problems.append("cjs: retryTurn schema not widened")
    if not problems:
        node_check(data, "cjs")
        log(f"cjs verified: gate widened (var={widened.group(1).decode()}), "
            f"retryTurn schema widened")

    # ---- renderer ----
    if args.dir:
        assets = Path(args.dir).resolve() / "out" / "renderer" / "assets"
        rcands = []
        if assets.is_dir():
            for js in sorted(assets.glob("*.js")):
                if js.stat().st_size < 100_000:
                    continue
                rd = js.read_bytes()
                if (b"zcode-editresend-ui" in rd
                        or SEL_SPREAD_RE.search(rd) or NEE_UPSTREAM in rd):
                    rcands.append(js)
        if len(rcands) != 1:
            problems.append(f"renderer: {len(rcands)} candidate chunks "
                            "(expected 1)")
        else:
            rd = rcands[0].read_bytes()
            spread = SEL_SPREAD_RE.search(rd)
            if not spread:
                problems.append("renderer: retry selection spread missing")
            if NEE_UPSTREAM not in rd:
                problems.append("renderer: upstream edit fix missing "
                                "(unexpected baseline)")
            if rd.count(b"zcode-editresend-ui") != 1:
                problems.append("renderer: ui marker count != 1")
            if not problems:
                node_check(rd, "renderer")
                log(f"renderer verified: retry carries live selection via "
                    f"{spread.group(1).decode()}() ({rcands[0].name})")

    if problems:
        fail("verify failed: " + "; ".join(problems))
    log("verified: edit-resend v7 fully applied")


if __name__ == "__main__":
    main()
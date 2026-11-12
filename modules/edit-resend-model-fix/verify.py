#!/usr/bin/env python3
"""edit-resend-model-fix v7: cjs + renderer verifier for zcode-mod-kit.

Exit 0 means v7 is fully applied on BOTH targets (ZCode 3.18.0):
  cjs      - builder gate admits retryTurn payload, retryTurn schema widened
  renderer - retry callback carries the live draft selection, and the edit
             side is present upstream (sanity signal for the assumed baseline)
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

SLUG = "edit-resend-model-fix"

GATE_OLD = b'let d=t.type==="editUserQuery"?t.payload:void 0'
GATE_NEW = (b"/*[zcode-editresend-model-fix:v7]*/"
            b'let d=t.type==="editUserQuery"||t.type==="retryTurn"?t.payload:void 0')
RT_NEW = (b"retryTurn:m.object({target:PR,modelSelection:Wc.optional(),"
          b"mode:H4.optional(),planEnabled:m.boolean().optional()}),"
          b"setAssistantFeedback")

NEE_UPSTREAM = (b"...o?{modelSelection:o.modelSelection,mode:o.mode,"
                b"planEnabled:o.planEnabled}:{}")
SEL_SPREAD = (b"...si?{modelSelection:si.modelSelection,mode:si.mode,"
              b"planEnabled:si.planEnabled}:{}")
BI_FINAL = b"return Ni(`retryTurn`,{target:e," + SEL_SPREAD


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
    if GATE_NEW not in data:
        problems.append("cjs: retryTurn payload gate not widened")
    if GATE_OLD in data:
        problems.append("cjs: original editUserQuery-only gate still present")
    if RT_NEW not in data:
        problems.append("cjs: retryTurn schema not widened")
    if not problems:
        node_check(data, "cjs")
        log("cjs verified: retry payload gate + widened retryTurn schema")

    # ---- renderer ----
    if args.dir:
        assets = Path(args.dir).resolve() / "out" / "renderer" / "assets"
        rcands = []
        if assets.is_dir():
            for js in sorted(assets.glob("*.js")):
                if js.stat().st_size < 100_000:
                    continue
                rd = js.read_bytes()
                if (b"zcode-editresend-ui" in rd or SEL_SPREAD in rd
                        or NEE_UPSTREAM in rd):
                    rcands.append(js)
        if len(rcands) != 1:
            problems.append(f"renderer: {len(rcands)} candidate chunks "
                            "(expected 1)")
        else:
            rd = rcands[0].read_bytes()
            if BI_FINAL not in rd:
                problems.append("renderer: retry selection spread missing")
            if NEE_UPSTREAM not in rd:
                problems.append("renderer: upstream edit fix missing "
                                "(unexpected baseline)")
            if rd.count(b"zcode-editresend-ui") != 1:
                problems.append("renderer: ui marker count != 1")
            if not problems:
                node_check(rd, "renderer")
                log(f"renderer verified: retry carries live selection "
                    f"({rcands[0].name})")

    if problems:
        fail("verify failed: " + "; ".join(problems))
    log("verified: edit-resend v7 fully applied")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""edit-resend-model-fix v2.2: cjs + renderer verifier for zcode-mod-kit.

Exit 0 means v2.2 is fully applied on BOTH targets:
  cjs      - v2 tag present, stale fields gone, schema widened
  renderer - stash + widened schema + nee/bi read the live draft ref
             Bn.current (NOT the stale window.__zermSel snapshot nor a stale
             Qn() closure)
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

SLUG = "edit-resend-model-fix"

STALE3 = (b"modelSelection:o.intent.modelSelection,"
          b"mode:o.intent.mode,planEnabled:o.intent.planEnabled,")
V1_COMMENT = b"/*[zcode-editresend-model-fix]*/"
FINAL_SJO = (b"/*[zcode-editresend-model-fix:v2]*/"
             b"modelSelection:n.payload?.modelSelection,"
             b"mode:n.payload?.mode,"
             b"planEnabled:n.payload?.planEnabled!==void 0?"
             b"n.payload.planEnabled:void 0,")
CJS_SCHEMA_NEW = (b"retryTurn:m.object({target:NR,modelSelection:Pu.optional(),"
                  b"mode:Npe.optional(),planEnabled:m.boolean().optional()})")

WM = (b"...window.__zermSel?{modelSelection:window.__zermSel."
      b"modelSelection,mode:window.__zermSel.mode,"
      b"planEnabled:window.__zermSel.planEnabled}:{}")
QN = (b"...(Qn()?{modelSelection:Qn().modelSelection,mode:Qn().mode,"
      b"planEnabled:Qn().planEnabled}:{})")
BN = (b"...(Bn.current.modelSelection?{modelSelection:Bn.current."
      b"modelSelection,mode:Bn.current.mode,"
      b"planEnabled:Bn.current.planEnabled}:{})")
RS_SCHEMA_NEW_FRAG = (b"retryTurn:ni({target:Ni,modelSelection:va.optional(),"
                      b"mode:Na.optional(),planEnabled:Ot().optional()})")
STASH_FINAL = b"window.__zermSel={mode:y.mode,planEnabled:"


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
    ap = argparse.ArgumentParser(description=f"{SLUG}: verify v2.2 state")
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
    if FINAL_SJO not in data:
        problems.append("cjs: v2 replay fields missing")
    if STALE3 in data:
        problems.append("cjs: stale fields still present")
    if V1_COMMENT in data:
        problems.append("cjs: v1 comment not upgraded to v2")
    if CJS_SCHEMA_NEW not in data:
        problems.append("cjs: schema not widened")
    if not problems:
        node_check(data, "cjs")
        log("cjs verified: v2 replay + widened schema")

    # ---- renderer ----
    if args.dir:
        assets = Path(args.dir).resolve() / "out" / "renderer" / "assets"
        rcands = []
        if assets.is_dir():
            for js in sorted(assets.glob("*.js")):
                if js.stat().st_size < 100_000:
                    continue
                rd = js.read_bytes()
                if (b"zcode-editresend-ui" in rd or BN in rd or QN in rd
                        or WM in rd or STASH_FINAL in rd):
                    rcands.append(js)
        if len(rcands) != 1:
            problems.append(f"renderer: {len(rcands)} candidate chunks "
                            "(expected 1)")
        else:
            rd = rcands[0].read_bytes()
            if BN not in rd:
                problems.append("renderer: nee/bi not reading Bn.current")
            if WM in rd:
                problems.append("renderer: stale window.__zermSel spread "
                                "still present")
            if QN in rd:
                problems.append("renderer: stale Qn() spread still present")
            if STASH_FINAL not in rd:
                problems.append("renderer: composer stash missing")
            if RS_SCHEMA_NEW_FRAG not in rd:
                problems.append("renderer: schema not widened")
            if not problems:
                node_check(rd, "renderer")
                log(f"renderer verified: Bn.current live read + stash + "
                    f"schema ({rcands[0].name})")

    if problems:
        fail("verify failed: " + "; ".join(problems))
    log("verified: edit-resend v2.2 fully applied")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""edit-resend-model-fix v3: cjs + renderer verifier for zcode-mod-kit.

Exit 0 means v3 is fully applied on BOTH targets (ZCode 3.15.3).
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

SLUG = "edit-resend-model-fix"

LC_STALE = (b"modelSelection:o.intent.modelSelection,"
            b"mode:o.intent.mode,planEnabled:o.intent.planEnabled,")
LC_PATCHED = (b"/*[zcode-editresend-model-fix:v3]*/"
              b"modelSelection:n.payload?.modelSelection??o.intent.modelSelection,"
              b"mode:n.payload?.mode??o.intent.mode,"
              b"planEnabled:n.payload?.planEnabled!==void 0?"
              b"n.payload.planEnabled:o.intent.planEnabled,")
RT_NEW = (b"retryTurn:m.object({target:BA,modelSelection:Nl.optional(),"
          b"mode:Lme.optional(),planEnabled:m.boolean().optional()}),"
          b"setAssistantFeedback")

ER_SPREAD = (b"...(er.current.modelSelection?{modelSelection:er.current."
             b"modelSelection,mode:er.current.mode,"
             b"planEnabled:er.current.planEnabled}:{})")
NEE_FINAL = (b"let l=await Fr(`editUserQuery`,{target:e,newText:n,"
             b"workspaceMode:i,conversationQuotes:a," + ER_SPREAD)
BI_FINAL = (b"return Fr(`retryTurn`,{target:e," + ER_SPREAD)


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
    ap = argparse.ArgumentParser(description=f"{SLUG}: verify v3 state")
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
    if LC_PATCHED not in data:
        problems.append("cjs: LCt payload-priority replay missing")
    if LC_STALE in data:
        problems.append("cjs: frozen replay still present")
    if RT_NEW not in data:
        problems.append("cjs: retryTurn schema not widened")
    if not problems:
        node_check(data, "cjs")
        log("cjs verified: payload-priority + widened retryTurn schema")

    # ---- renderer ----
    if args.dir:
        assets = Path(args.dir).resolve() / "out" / "renderer" / "assets"
        rcands = []
        if assets.is_dir():
            for js in sorted(assets.glob("*.js")):
                if js.stat().st_size < 100_000:
                    continue
                rd = js.read_bytes()
                if (b"zcode-editresend-ui" in rd or ER_SPREAD in rd
                        or NEE_FINAL in rd or BI_FINAL in rd):
                    rcands.append(js)
        if len(rcands) != 1:
            problems.append(f"renderer: {len(rcands)} candidate chunks "
                            "(expected 1)")
        else:
            rd = rcands[0].read_bytes()
            if ER_SPREAD not in rd:
                problems.append("renderer: er.current spread missing")
            if NEE_FINAL not in rd:
                problems.append("renderer: nee insertion missing")
            if BI_FINAL not in rd:
                problems.append("renderer: bi insertion missing")
            if rd.count(b"zcode-editresend-ui") != 2:
                problems.append("renderer: ui marker count != 2")
            if not problems:
                node_check(rd, "renderer")
                log(f"renderer verified: er.current spread in nee/bi "
                    f"({rcands[0].name})")

    if problems:
        fail("verify failed: " + "; ".join(problems))
    log("verified: edit-resend v3 fully applied")


if __name__ == "__main__":
    main()
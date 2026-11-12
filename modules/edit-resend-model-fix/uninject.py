#!/usr/bin/env python3
"""edit-resend-model-fix v7: cjs + renderer uninjector for zcode-mod-kit.

Reverses v7 back to the OFFICIAL 3.18.0 state, byte-exactly, on both targets.
The edit path is untouched by v7 (fixed upstream), so only the retry-side
patches are reverted.
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
RT_OLD = b"retryTurn:m.object({target:PR}),setAssistantFeedback"
RT_NEW = (b"retryTurn:m.object({target:PR,modelSelection:Wc.optional(),"
          b"mode:H4.optional(),planEnabled:m.boolean().optional()}),"
          b"setAssistantFeedback")

SEL_SPREAD = (b"...si?{modelSelection:si.modelSelection,mode:si.mode,"
              b"planEnabled:si.planEnabled}:{}")
BI_NEW = (b"return Ni(`retryTurn`,{target:e," + SEL_SPREAD +
          b"},t,n.revision,n.logEpoch)}/*[zcode-editresend-ui]*/,[Ni,t])")
BI_OLD = b"return Ni(`retryTurn`,{target:e},t,n.revision,n.logEpoch)},[Ni,t])"


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


def uninject_cjs(tpath: Path) -> None:
    data = tpath.read_bytes()
    touched = False

    if GATE_NEW in data:
        if data.count(GATE_NEW) != 1:
            fail("cjs builder gate patch matched != 1; abort", 2)
        data = data.replace(GATE_NEW, GATE_OLD, 1)
        touched = True
        log("cjs L1: builder gate restored to editUserQuery-only")
    elif GATE_OLD in data:
        log("cjs L1: no patch present")

    if RT_NEW in data:
        if data.count(RT_NEW) != 1:
            fail("cjs retryTurn widened schema matched != 1; abort", 2)
        data = data.replace(RT_NEW, RT_OLD, 1)
        touched = True
        log("cjs L2: retryTurn schema unwidened")

    if touched:
        node_check(data, "cjs")
        tpath.write_bytes(data)
        log("cjs uninjected")


def renderer_candidates(root: Path):
    assets = root / "out" / "renderer" / "assets"
    if not assets.is_dir():
        fail(f"renderer assets dir not found: {assets}")
    keys = [b"zcode-editresend-ui", SEL_SPREAD, BI_OLD]
    for js in sorted(assets.glob("*.js")):
        if js.stat().st_size < 100_000:
            continue
        data = js.read_bytes()
        if any(k in data for k in keys):
            yield js, data


def uninject_renderer(root: Path) -> None:
    cands = list(renderer_candidates(root))
    if not cands:
        log("renderer: nothing to uninject")
        return
    if len(cands) > 1:
        fail(f"renderer: anchors matched {len(cands)} chunks; refusing", 2)
    rpath, data = cands[0]
    log(f"renderer target: {rpath.name}")
    touched = False

    if BI_NEW in data:
        if data.count(BI_NEW) != 1:
            fail("renderer retry patch matched != 1; abort", 2)
        data = data.replace(BI_NEW, BI_OLD, 1)
        touched = True
        log("renderer retry: reverted")

    if b"zcode-editresend-ui" in data or SEL_SPREAD in data:
        fail("renderer: stray editresend markers remain; abort", 2)

    if touched:
        node_check(data, "renderer")
        rpath.write_bytes(data)
        log("renderer uninjected")


def main() -> None:
    ap = argparse.ArgumentParser(description=f"{SLUG}: un-inject v7 fix")
    ap.add_argument("--dir", default=None, help="unpacked asar root")
    ap.add_argument("--zcode-cjs", default=None,
                    help="path to resources/glm/zcode.cjs")
    ap.add_argument("--install-root", default=None, help=argparse.SUPPRESS)
    args = ap.parse_args()

    if not args.zcode_cjs:
        fail("missing --zcode-cjs path")
    cjs = Path(args.zcode_cjs).resolve()
    if not cjs.is_file():
        fail(f"zcode.cjs not found: {cjs}")
    uninject_cjs(cjs)

    if args.dir:
        uninject_renderer(Path(args.dir).resolve())


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""edit-resend-model-fix v6: cjs + renderer uninjector for zcode-mod-kit.

Reverses v6 back to the OFFICIAL 3.17.2 state, byte-exactly, on both targets.
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

SLUG = "edit-resend-model-fix"

RI_STALE = (b"modelSelection:n.intent.modelSelection,"
             b"mode:n.intent.mode,planEnabled:n.intent.planEnabled,")
RI_PATCHED = (b"/*[zcode-editresend-model-fix:v6]*/"
               b"modelSelection:t.payload?.modelSelection??n.intent.modelSelection,"
               b"mode:t.payload?.mode??n.intent.mode,"
               b"planEnabled:t.payload?.planEnabled!==void 0?"
               b"t.payload.planEnabled:n.intent.planEnabled,")
RT_OLD = (b"retryTurn:m.object({target:lP}),setAssistantFeedback")
RT_NEW = (b"retryTurn:m.object({target:lP,modelSelection:Nl.optional(),"
          b"mode:Cge.optional(),planEnabled:m.boolean().optional()}),"
          b"setAssistantFeedback")

NR_SPREAD = (b"...(Nr.current.modelSelection?{modelSelection:Nr.current."
             b"modelSelection,mode:Nr.current.mode,"
             b"planEnabled:Nr.current.planEnabled}:{})")
NEE_NEW = (b"let l=await Ci(`editUserQuery`,{target:e,newText:n,"
           b"workspaceMode:i,conversationQuotes:a," + NR_SPREAD +
           b",...r?{attachments:[...r]}:{},...s.override},t,c.revision,"
           b"c.logEpoch,void 0,s.acceleratedCard);"
           b"/*[zcode-editresend-ui]*/")
NEE_OLD = (b"let l=await Ci(`editUserQuery`,{target:e,newText:n,"
           b"workspaceMode:i,conversationQuotes:a,"
           b"...r?{attachments:[...r]}:{},...s.override},t,c.revision,"
           b"c.logEpoch,void 0,s.acceleratedCard);")
BI_NEW = (b"return Ci(`retryTurn`,{target:e," + NR_SPREAD +
          b"}/*[zcode-editresend-ui]*/,t,n.revision,n.logEpoch)")
BI_OLD = b"return Ci(`retryTurn`,{target:e},t,n.revision,n.logEpoch)"


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

    if RI_PATCHED in data:
        if data.count(RI_PATCHED) != 1:
            fail("cjs r_i v6 patch matched != 1; abort", 2)
        data = data.replace(RI_PATCHED, RI_STALE, 1)
        touched = True
        log("cjs L1: r_i restored to official frozen replay")
    elif RI_STALE in data:
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
    keys = [b"zcode-editresend-ui", NR_SPREAD, NEE_OLD, BI_OLD]
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

    if NEE_NEW in data:
        if data.count(NEE_NEW) != 1:
            fail("renderer nee patch matched != 1; abort", 2)
        data = data.replace(NEE_NEW, NEE_OLD, 1)
        touched = True
        log("renderer nee: reverted")
    if BI_NEW in data:
        if data.count(BI_NEW) != 1:
            fail("renderer retry patch matched != 1; abort", 2)
        data = data.replace(BI_NEW, BI_OLD, 1)
        touched = True
        log("renderer retry: reverted")

    if b"zcode-editresend-ui" in data or NR_SPREAD in data:
        fail("renderer: stray editresend markers remain; abort", 2)

    if touched:
        node_check(data, "renderer")
        rpath.write_bytes(data)
        log("renderer uninjected")


def main() -> None:
    ap = argparse.ArgumentParser(description=f"{SLUG}: un-inject v6 fix")
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
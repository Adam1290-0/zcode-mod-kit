#!/usr/bin/env python3
"""edit-resend-model-fix v4: cjs + renderer uninjector for zcode-mod-kit.

Reverses v4 back to the OFFICIAL 3.16.2 state, byte-exactly, on both targets.
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

SLUG = "edit-resend-model-fix"

BDI_STALE = (b"modelSelection:n.intent.modelSelection,"
             b"mode:n.intent.mode,planEnabled:n.intent.planEnabled,")
BDI_PATCHED = (b"/*[zcode-editresend-model-fix:v4]*/"
               b"modelSelection:t.payload?.modelSelection??n.intent.modelSelection,"
               b"mode:t.payload?.mode??n.intent.mode,"
               b"planEnabled:t.payload?.planEnabled!==void 0?"
               b"t.payload.planEnabled:n.intent.planEnabled,")
RT_OLD = (b"retryTurn:m.object({target:KA}),setAssistantFeedback")
RT_NEW = (b"retryTurn:m.object({target:KA,modelSelection:Ll.optional(),"
          b"mode:Che.optional(),planEnabled:m.boolean().optional()}),"
          b"setAssistantFeedback")

ER_SPREAD = (b"...(Er.current.modelSelection?{modelSelection:Er.current."
             b"modelSelection,mode:Er.current.mode,"
             b"planEnabled:Er.current.planEnabled}:{})")
NEE_NEW = (b"let l=await li(`editUserQuery`,{target:e,newText:n,"
           b"workspaceMode:i,conversationQuotes:a," + ER_SPREAD +
           b",...r?{attachments:[...r]}:{},...s.override},t,c.revision,"
           b"c.logEpoch,void 0,s.acceleratedCard);"
           b"/*[zcode-editresend-ui]*/")
NEE_OLD = (b"let l=await li(`editUserQuery`,{target:e,newText:n,"
           b"workspaceMode:i,conversationQuotes:a,"
           b"...r?{attachments:[...r]}:{},...s.override},t,c.revision,"
           b"c.logEpoch,void 0,s.acceleratedCard);")
BI_NEW = (b"return li(`retryTurn`,{target:e," + ER_SPREAD +
          b"}/*[zcode-editresend-ui]*/,t,n.revision,n.logEpoch)")
BI_OLD = b"return li(`retryTurn`,{target:e},t,n.revision,n.logEpoch)"


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

    if BDI_PATCHED in data:
        if data.count(BDI_PATCHED) != 1:
            fail("cjs bdi v4 patch matched != 1; abort", 2)
        data = data.replace(BDI_PATCHED, BDI_STALE, 1)
        touched = True
        log("cjs L1: bdi restored to official frozen replay")
    elif BDI_STALE in data:
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
    keys = [b"zcode-editresend-ui", ER_SPREAD, NEE_OLD, BI_OLD]
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

    if b"zcode-editresend-ui" in data or ER_SPREAD in data:
        fail("renderer: stray editresend markers remain; abort", 2)

    if touched:
        node_check(data, "renderer")
        rpath.write_bytes(data)
        log("renderer uninjected")


def main() -> None:
    ap = argparse.ArgumentParser(description=f"{SLUG}: un-inject v4 fix")
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
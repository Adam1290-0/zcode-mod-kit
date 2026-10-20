#!/usr/bin/env python3
"""edit-resend-model-fix v4: cjs + renderer injector for zcode-mod-kit.

GOAL: "edit user query" / "retry turn" must run with the model the user has
CURRENTLY selected in the composer (ZCode 3.16.2).

Why still needed in 3.16.2: the official editUserQuery schema already accepts
payload.modelSelection (highspeed path), but the canonical-intent builder
bdi() still replays the FROZEN modelSelection/mode/planEnabled from the
original intent, and retryTurn still has no selection fields at all; the
renderer edit/retry callbacks still do not attach the current composer
selection.

Structural note (3.16.2): the v3 target LCt was split into
bdi (buildCanonicalIntent) + zAt (startCanonicalIntent); BOTH editUserQuery
and retryTurn (bfc executor: Ijn + zAt) funnel through bdi, so patching bdi's
frozen replay covers every re-run path in one anchor.

Patches (all anchors verified unique in 3.16.2):

cjs L1   bdi frozen replay -> payload-priority
cjs L2   retryTurn schema widened with optional modelSelection/mode/planEnabled
renderer L3  nee/retry callbacks spread the live draft ref Er.current
         (draftConfigRef useRef, updated synchronously by the draft updater -
         the v2 lesson: never a render snapshot or memoized callback closure).

No renderer schema work needed: the renderer transport does not strip payload
fields client-side (verified on the `li` dispatcher).
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

SLUG = "edit-resend-model-fix"
V4_TAG = b"/*[zcode-editresend-model-fix:v4]*/"

# ----------------------------- cjs anchors (3.16.2) ------------------------
BDI_STALE = (b"modelSelection:n.intent.modelSelection,"
             b"mode:n.intent.mode,planEnabled:n.intent.planEnabled,")
BDI_PATCHED = (V4_TAG
               + b"modelSelection:t.payload?.modelSelection??n.intent.modelSelection,"
               b"mode:t.payload?.mode??n.intent.mode,"
               b"planEnabled:t.payload?.planEnabled!==void 0?"
               b"t.payload.planEnabled:n.intent.planEnabled,")
RT_OLD = (b"retryTurn:m.object({target:KA}),setAssistantFeedback")
RT_NEW = (b"retryTurn:m.object({target:KA,modelSelection:Ll.optional(),"
          b"mode:Che.optional(),planEnabled:m.boolean().optional()}),"
          b"setAssistantFeedback")

# --------------------------- renderer anchors (3.16.2) --------------------
NEE_OLD = (b"let l=await li(`editUserQuery`,{target:e,newText:n,"
           b"workspaceMode:i,conversationQuotes:a,"
           b"...r?{attachments:[...r]}:{},...s.override},t,c.revision,"
           b"c.logEpoch,void 0,s.acceleratedCard);")
ER_SPREAD = (b"...(Er.current.modelSelection?{modelSelection:Er.current."
             b"modelSelection,mode:Er.current.mode,"
             b"planEnabled:Er.current.planEnabled}:{})")
NEE_NEW = (b"let l=await li(`editUserQuery`,{target:e,newText:n,"
           b"workspaceMode:i,conversationQuotes:a," + ER_SPREAD +
           b",...r?{attachments:[...r]}:{},...s.override},t,c.revision,"
           b"c.logEpoch,void 0,s.acceleratedCard);"
           b"/*[zcode-editresend-ui]*/")
BI_OLD = b"return li(`retryTurn`,{target:e},t,n.revision,n.logEpoch)"
BI_NEW = (b"return li(`retryTurn`,{target:e," + ER_SPREAD +
          b"}/*[zcode-editresend-ui]*/,t,n.revision,n.logEpoch)")


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


def patch_cjs(tpath: Path) -> None:
    data = tpath.read_bytes()
    changed = False

    if BDI_PATCHED in data:
        log("cjs L1: bdi already payload-priority, skip")
    elif BDI_STALE in data:
        n = data.count(BDI_STALE)
        if n != 1:
            fail(f"cjs bdi frozen-replay anchor matched {n} times (expected "
                 "1)", 2)
        data = data.replace(BDI_STALE, BDI_PATCHED, 1)
        changed = True
        log("cjs L1: bdi frozen replay -> payload-priority")
    else:
        fail("cjs L1: neither pristine anchor nor v4 tag found (version "
             "drift?)", 2)

    if RT_NEW in data:
        log("cjs L2: retryTurn schema already widened, skip")
    else:
        n = data.count(RT_OLD)
        if n != 1:
            fail(f"cjs retryTurn schema anchor matched {n} times (expected "
                 "1)", 2)
        data = data.replace(RT_OLD, RT_NEW, 1)
        changed = True
        log("cjs L2: retryTurn schema widened")

    if changed:
        node_check(data, "cjs")
        tpath.write_bytes(data)


def renderer_candidates(root: Path):
    assets = root / "out" / "renderer" / "assets"
    if not assets.is_dir():
        fail(f"renderer assets dir not found: {assets}")
    keys = [NEE_OLD, BI_OLD, ER_SPREAD, b"zcode-editresend-ui"]
    for js in sorted(assets.glob("*.js")):
        if js.stat().st_size < 100_000:
            continue
        data = js.read_bytes()
        if any(k in data for k in keys):
            yield js, data


def patch_renderer(root: Path) -> None:
    cands = list(renderer_candidates(root))
    if not cands:
        fail("renderer: no chunk contains edit-resend anchors (version "
             "drift in hashed bundle?)", 2)
    if len(cands) > 1:
        fail(f"renderer: anchors matched {len(cands)} chunks; refusing", 2)
    rpath, data = cands[0]
    log(f"renderer target: {rpath.name}")
    changed = False

    for name, old, new in [
        ("nee", NEE_OLD, NEE_NEW),
        ("bi", BI_OLD, BI_NEW),
    ]:
        if new in data:
            log(f"renderer {name}: already applied, skip")
            continue
        n = data.count(old)
        if n != 1:
            fail(f"renderer {name} anchor matched {n} times (expected 1)", 2)
        data = data.replace(old, new, 1)
        changed = True
        log(f"renderer {name}: Er.current selection spread applied")

    if not changed:
        log("renderer: already injected, skip")
        return
    node_check(data, "renderer")
    rpath.write_bytes(data)


def main() -> None:
    ap = argparse.ArgumentParser(description=f"{SLUG}: inject v4 fix")
    ap.add_argument("--dir", default=None, help="unpacked asar root")
    ap.add_argument("--zcode-cjs", default=None,
                    help="path to resources/glm/zcode.cjs")
    ap.add_argument("--install-root", default=None, help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.zcode_cjs:
        cjs = Path(args.zcode_cjs).resolve()
        if not cjs.is_file():
            fail(f"zcode.cjs not found: {cjs}")
        log(f"cjs target: {cjs}")
        patch_cjs(cjs)
    else:
        fail("missing --zcode-cjs path")

    if args.dir:
        patch_renderer(Path(args.dir).resolve())
    else:
        log("no --dir given, renderer patch skipped")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""edit-resend-model-fix v6: cjs + renderer injector for zcode-mod-kit.

GOAL: "edit user query" / "retry turn" must run with the model the user has
CURRENTLY selected in the composer (ZCode 3.17.2).

Why still needed in 3.17.2: the official editUserQuery schema already accepts
payload.modelSelection (highspeed path), but the canonical-intent builder
still replays the FROZEN modelSelection/mode/planEnabled from the original
intent, and retryTurn still has no selection fields at all; the renderer
edit/retry callbacks still do not attach the current composer selection.

Structural note (3.17.2): the builder that carries the frozen replay is the
function named r_i (it was bdi in 3.16.x). The minified name "bdi" in 3.17.2
belongs to an unrelated session-resource-close helper, so anchors here are
matched by their literal payload text, never by function name.

Patches (all anchors verified unique in 3.17.2):

cjs L1   r_i frozen replay -> payload-priority
cjs L2   retryTurn schema widened with optional modelSelection/mode/planEnabled
renderer L3  nee/retry callbacks spread the live draft ref Nr.current
         (draftConfigRef useRef, updated synchronously by the draft updater -
         the v2 lesson: never a render snapshot or memoized callback closure).

No renderer schema work needed: the renderer transport does not strip payload
fields client-side (verified on the `Ci` dispatcher).
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

SLUG = "edit-resend-model-fix"
V6_TAG = b"/*[zcode-editresend-model-fix:v6]*/"

# ----------------------------- cjs anchors (3.17.2) ------------------------
RI_STALE = (b"modelSelection:n.intent.modelSelection,"
             b"mode:n.intent.mode,planEnabled:n.intent.planEnabled,")
RI_PATCHED = (V6_TAG
               + b"modelSelection:t.payload?.modelSelection??n.intent.modelSelection,"
               b"mode:t.payload?.mode??n.intent.mode,"
               b"planEnabled:t.payload?.planEnabled!==void 0?"
               b"t.payload.planEnabled:n.intent.planEnabled,")
RT_OLD = (b"retryTurn:m.object({target:lP}),setAssistantFeedback")
RT_NEW = (b"retryTurn:m.object({target:lP,modelSelection:Nl.optional(),"
          b"mode:Cge.optional(),planEnabled:m.boolean().optional()}),"
          b"setAssistantFeedback")

# --------------------------- renderer anchors (3.17.2) --------------------
NEE_OLD = (b"let l=await Ci(`editUserQuery`,{target:e,newText:n,"
           b"workspaceMode:i,conversationQuotes:a,"
           b"...r?{attachments:[...r]}:{},...s.override},t,c.revision,"
           b"c.logEpoch,void 0,s.acceleratedCard);")
NR_SPREAD = (b"...(Nr.current.modelSelection?{modelSelection:Nr.current."
             b"modelSelection,mode:Nr.current.mode,"
             b"planEnabled:Nr.current.planEnabled}:{})")
NEE_NEW = (b"let l=await Ci(`editUserQuery`,{target:e,newText:n,"
           b"workspaceMode:i,conversationQuotes:a," + NR_SPREAD +
           b",...r?{attachments:[...r]}:{},...s.override},t,c.revision,"
           b"c.logEpoch,void 0,s.acceleratedCard);"
           b"/*[zcode-editresend-ui]*/")
BI_OLD = b"return Ci(`retryTurn`,{target:e},t,n.revision,n.logEpoch)"
BI_NEW = (b"return Ci(`retryTurn`,{target:e," + NR_SPREAD +
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

    if RI_PATCHED in data:
        log("cjs L1: r_i already payload-priority, skip")
    elif RI_STALE in data:
        n = data.count(RI_STALE)
        if n != 1:
            fail(f"cjs r_i frozen-replay anchor matched {n} times (expected "
                 "1)", 2)
        data = data.replace(RI_STALE, RI_PATCHED, 1)
        changed = True
        log("cjs L1: r_i frozen replay -> payload-priority")
    else:
        fail("cjs L1: neither pristine anchor nor v6 tag found (version "
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
    keys = [NEE_OLD, BI_OLD, NR_SPREAD, b"zcode-editresend-ui"]
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
        log(f"renderer {name}: Nr.current selection spread applied")

    if not changed:
        log("renderer: already injected, skip")
        return
    node_check(data, "renderer")
    rpath.write_bytes(data)


def main() -> None:
    ap = argparse.ArgumentParser(description=f"{SLUG}: inject v6 fix")
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
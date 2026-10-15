#!/usr/bin/env python3
"""edit-resend-model-fix v3: cjs + renderer injector for zcode-mod-kit.

GOAL: "edit user query" / "retry turn" must run with the model the user has
CURRENTLY selected in the composer (ZCode 3.15.3).

Why still needed in 3.15.3: the official editUserQuery schema now accepts
payload.modelSelection (added for the highspeed path), but the canonical
re-run (LCt) still replays the FROZEN modelSelection/mode/planEnabled from
the original intent; retryTurn still has no selection fields at all; and the
renderer edit (nee) / retry (zi) callbacks still do not attach the current
composer selection.

Patches (all anchors verified unique in 3.15.3):

cjs L1  LCt (startCanonicalIntent): frozen replay ->
        payload-priority (payload.modelSelection ?? intent.modelSelection, etc.)
cjs L2  retryTurn schema widened with optional modelSelection/mode/planEnabled
        (editUserQuery schema already carries modelSelection upstream).

renderer L3  nee/zi callbacks spread the live draft ref er.current
        (draftConfigRef, a useRef updated synchronously by the draft updater,
        so the value read at click time is always current - the v2 lesson:
        never read a render snapshot or a memoized callback closure).

No renderer schema work needed in 3.15.3: the renderer transport does not
strip payload fields client-side (no ni registry validation on this path).
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

SLUG = "edit-resend-model-fix"
V3_TAG = b"/*[zcode-editresend-model-fix:v3]*/"

# ----------------------------- cjs anchors (3.15.3) ------------------------
LC_STALE = (b"modelSelection:o.intent.modelSelection,"
            b"mode:o.intent.mode,planEnabled:o.intent.planEnabled,")
LC_PATCHED = (V3_TAG
              + b"modelSelection:n.payload?.modelSelection??o.intent.modelSelection,"
              b"mode:n.payload?.mode??o.intent.mode,"
              b"planEnabled:n.payload?.planEnabled!==void 0?"
              b"n.payload.planEnabled:o.intent.planEnabled,")
RT_OLD = (b"retryTurn:m.object({target:BA}),setAssistantFeedback")
RT_NEW = (b"retryTurn:m.object({target:BA,modelSelection:Nl.optional(),"
          b"mode:Lme.optional(),planEnabled:m.boolean().optional()}),"
          b"setAssistantFeedback")

# --------------------------- renderer anchors (3.15.3) --------------------
NEE_OLD = (b"let l=await Fr(`editUserQuery`,{target:e,newText:n,"
           b"workspaceMode:i,conversationQuotes:a,"
           b"...r?{attachments:[...r]}:{},...s.override},t,c.revision,"
           b"c.logEpoch,void 0,s.acceleratedCard);")
ER_SPREAD = (b"...(er.current.modelSelection?{modelSelection:er.current."
             b"modelSelection,mode:er.current.mode,"
             b"planEnabled:er.current.planEnabled}:{})")
NEE_NEW = (b"let l=await Fr(`editUserQuery`,{target:e,newText:n,"
           b"workspaceMode:i,conversationQuotes:a," + ER_SPREAD +
           b",...r?{attachments:[...r]}:{},...s.override},t,c.revision,"
           b"c.logEpoch,void 0,s.acceleratedCard);"
           b"/*[zcode-editresend-ui]*/")
BI_OLD = b"return Fr(`retryTurn`,{target:e},t,n.revision,n.logEpoch)"
BI_NEW = (b"return Fr(`retryTurn`,{target:e," + ER_SPREAD +
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

    if LC_PATCHED in data:
        log("cjs L1: LCt already payload-priority, skip")
    elif LC_STALE in data:
        n = data.count(LC_STALE)
        if n != 1:
            fail(f"cjs LCt frozen-replay anchor matched {n} times (expected "
                 "1)", 2)
        data = data.replace(LC_STALE, LC_PATCHED, 1)
        changed = True
        log("cjs L1: LCt frozen replay -> payload-priority")
    else:
        fail("cjs L1: neither pristine anchor nor v3 tag found (version "
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
        log(f"renderer {name}: er.current selection spread applied")

    if not changed:
        log("renderer: already injected, skip")
        return
    node_check(data, "renderer")
    rpath.write_bytes(data)


def main() -> None:
    ap = argparse.ArgumentParser(description=f"{SLUG}: inject v3 fix")
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
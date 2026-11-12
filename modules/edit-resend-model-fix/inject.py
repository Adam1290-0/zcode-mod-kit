#!/usr/bin/env python3
"""edit-resend-model-fix v7: cjs + renderer injector for zcode-mod-kit.

GOAL: "retry turn" must run with the model the user has CURRENTLY selected.

STATUS CHANGE in ZCode 3.18.0 - the EDIT path is now fixed upstream:
  * cjs builder D1i resolves `modelSelection: d?.modelSelection ??
    n.intent.modelSelection` where d = payload for editUserQuery.
  * renderer edit callback qa() takes a 6th arg `o = si()` (useMemo over the
    draftConfigRef Vr, i.e. the live draft) and spreads
    `...(o?{modelSelection:o.modelSelection,mode:o.mode,planEnabled:o.planEnabled}:{})`
    into the payload.
  That is the design this module introduced (v2.2 read-ref + payload
  priority), so the module no longer patches the edit path.

STILL BROKEN in 3.18.0 - retryTurn:
  * the builder gate is `t.type==="editUserQuery" ? t.payload : void 0`, so a
    retryTurn command contributes no payload and the FROZEN intent values win;
  * cjs retryTurn schema is still `{target:PR}` - zod would strip selection
    fields even if they were sent;
  * the renderer retry callback still sends `Ni(`retryTurn`,{target:e},...)`
    with no selection.

v7 therefore has three anchors, all on the retry path:
  cjs L1  builder gate also admits retryTurn payload
  cjs L2  retryTurn schema widened (same aliases the edit schema already uses)
  rndr    retry callback carries the live draft selection (same `si` memo the
          upstream edit callback uses, so both paths stay consistent)
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

SLUG = "edit-resend-model-fix"
V7_TAG = b"/*[zcode-editresend-model-fix:v7]*/"

# ----------------------------- cjs anchors (3.18.0) ------------------------
GATE_OLD = b'let d=t.type==="editUserQuery"?t.payload:void 0'
GATE_NEW = (V7_TAG +
            b'let d=t.type==="editUserQuery"||t.type==="retryTurn"?t.payload:void 0')

RT_OLD = b"retryTurn:m.object({target:PR}),setAssistantFeedback"
# Schema aliases MUST come from the sibling editUserQuery schema in the same
# scope, not from anywhere else in the file: minified names are reused across
# unrelated scopes, and `Nl`/`Cge` (taken from a grep hit elsewhere in the
# bundle) resolve to other values - `Nl` is a number-or-variable in an
# unrelated TS-compiler section, so `Nl.optional()` crashed the storage
# prepare worker with "Nl is not defined" and ZCode failed to boot with
# transport_closed (2026-11-12). editUserQuery (verified on 3.18.0) uses
# modelSelection:Wc / mode:H4 / planEnabled:m.boolean().
RT_NEW = (b"retryTurn:m.object({target:PR,modelSelection:Wc.optional(),"
          b"mode:H4.optional(),planEnabled:m.boolean().optional()}),"
          b"setAssistantFeedback")

# --------------------------- renderer anchors (3.18.0) --------------------
NEE_UPSTREAM = (b"...o?{modelSelection:o.modelSelection,mode:o.mode,"
                b"planEnabled:o.planEnabled}:{}")
BI_OLD = b"return Ni(`retryTurn`,{target:e},t,n.revision,n.logEpoch)},[Ni,t])"
SEL_SPREAD = (b"...si?{modelSelection:si.modelSelection,mode:si.mode,"
              b"planEnabled:si.planEnabled}:{}")
BI_NEW = (b"return Ni(`retryTurn`,{target:e," + SEL_SPREAD +
          b"},t,n.revision,n.logEpoch)}/*[zcode-editresend-ui]*/,[Ni,t])")


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

    if GATE_NEW in data:
        log("cjs L1: builder gate already widened, skip")
    elif GATE_OLD in data:
        n = data.count(GATE_OLD)
        if n != 1:
            fail(f"cjs builder-gate anchor matched {n} times (expected 1)", 2)
        data = data.replace(GATE_OLD, GATE_NEW, 1)
        changed = True
        log("cjs L1: builder payload gate now covers retryTurn")
    else:
        fail("cjs L1: builder-gate anchor not found (version drift?)", 2)

    if RT_NEW in data:
        log("cjs L2: retryTurn schema already widened, skip")
    else:
        n = data.count(RT_OLD)
        if n != 1:
            fail(f"cjs retryTurn schema anchor matched {n} times (expected 1)",
                 2)
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
    keys = [BI_OLD, BI_NEW, NEE_UPSTREAM, b"zcode-editresend-ui"]
    for js in sorted(assets.glob("*.js")):
        if js.stat().st_size < 100_000:
            continue
        data = js.read_bytes()
        if any(k in data for k in keys):
            yield js, data


def patch_renderer(root: Path) -> None:
    cands = list(renderer_candidates(root))
    if not cands:
        fail("renderer: no chunk contains retry anchors (version drift?)", 2)
    if len(cands) > 1:
        fail(f"renderer: anchors matched {len(cands)} chunks; refusing", 2)
    rpath, data = cands[0]
    log(f"renderer target: {rpath.name}")

    if NEE_UPSTREAM not in data:
        fail("renderer: upstream edit-side selection spread not found - the "
             "edit path looks unfixed in this build; re-verify the edit path "
             "before trusting v7", 2)
    log("renderer: edit side already fixed upstream, no patch needed")

    if BI_NEW in data:
        log("renderer: retry already carries selection, skip")
        return
    n = data.count(BI_OLD)
    if n != 1:
        fail(f"renderer retry anchor matched {n} times (expected 1)", 2)
    data = data.replace(BI_OLD, BI_NEW, 1)
    log("renderer: retry callback now carries live draft selection (si)")

    node_check(data, "renderer")
    rpath.write_bytes(data)


def main() -> None:
    ap = argparse.ArgumentParser(description=f"{SLUG}: inject v7 fix")
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
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
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SLUG = "edit-resend-model-fix"
V7_TAG = b"/*[zcode-editresend-model-fix:v7]*/"

# ----------------------------- cjs anchors --------------------------------
# The gate's local variable name changes per build (d in 3.18.x, p in 3.19.1),
# so match the surrounding text and capture the name instead of hardcoding it.
GATE_RE = re.compile(
    rb'let ([A-Za-z_$][\w$]*)=t\.type==="editUserQuery"\?t\.payload:void 0')
# Already-patched form: the marker comment precedes the widened assignment.
GATE_INJECTED_RE = re.compile(
    rb'/\*\[zcode-editresend-model-fix:v7\]\*/let ([\w$]+)=t\.type==="'
    rb'editUserQuery"\|\|t\.type==="retryTurn"\?t\.payload:void 0')

RT_OLD = b"retryTurn:m.object({target:PR}),setAssistantFeedback"
RT_OLD_3182 = b"retryTurn:m.object({target:DR}),setAssistantFeedback"
# Schema aliases MUST come from the sibling editUserQuery schema in the same
# scope, not from anywhere else in the file: minified names are reused across
# unrelated scopes, and `Nl`/`Cge` (taken from a grep hit elsewhere in the
# bundle) resolve to other values - `Nl` is a number-or-variable in an
# unrelated TS-compiler section, so `Nl.optional()` crashed the storage
# prepare worker with "Nl is not defined" and ZCode failed to boot with
# transport_closed (2026-11-12).
# Verified alias sets: 3.18.0 PR/Wc/H4 - 3.18.2 DR/Wc/J4 - 3.19.1 $R/qc/fj.
# Never carry an alias across versions; the module derives them at run time.
RT_NEW = (b"retryTurn:m.object({target:PR,modelSelection:Wc.optional(),"
          b"mode:H4.optional(),planEnabled:m.boolean().optional()}),"
          b"setAssistantFeedback")
RT_NEW_3182 = (b"retryTurn:m.object({target:DR,modelSelection:Wc.optional(),"
               b"mode:J4.optional(),planEnabled:m.boolean().optional()}),"
               b"setAssistantFeedback")

# Guard against the class of bug above: derive the live aliases straight from
# the sibling editUserQuery schema before touching anything. A drifted alias
# is a hard failure, never a silent patch. The zod binding itself (m in
# 3.18.x, d in 3.19.1) must stay a wildcard or every upgrade breaks the guard.
EDIT_SCHEMA_RE = re.compile(
    rb'editUserQuery:[\w$]+\.object\(\{[^}]*?'
    rb'modelSelection:([\w$]+)\.optional\(\)[^}]*?'
    rb'mode:([\w$]+)\.optional\(\)')
RETRY_TARGET_RE = re.compile(
    rb"retryTurn:[\w$]+\.object\(\{target:([\w$]+)[,}]")

# --------------------------- renderer anchors ------------------------------
NEE_UPSTREAM = (b"...o?{modelSelection:o.modelSelection,mode:o.mode,"
                b"planEnabled:o.planEnabled}:{}")
BI_OLD = b"return Ni(`retryTurn`,{target:e},t,n.revision,n.logEpoch)},[Ni,t])"
# 3.18.2 renamed the dispatch helper Ni -> Mi and dropped the `si` selector;
# the composer submit-payload callback `ii()` sits in the same scope and
# returns the live {modelSelection,mode,planEnabled}, so read from it.
# `ii()` is evaluated exactly once via an IIFE parameter: a `let` cannot be
# declared inside an object literal, and three separate ii() calls would read
# the same ref three times for no benefit.
BI_OLD_3182 = b"return Mi(`retryTurn`,{target:e},t,n.revision,n.logEpoch)},[Mi,t])"
SEL_SPREAD = (b"...si?{modelSelection:si.modelSelection,mode:si.mode,"
              b"planEnabled:si.planEnabled}:{}")
SEL_SPREAD_3182 = (b"...((_r)=>_r?{modelSelection:_r.modelSelection,"
                   b"mode:_r.mode,planEnabled:_r.planEnabled}:{})(ii())")
BI_NEW = (b"return Ni(`retryTurn`,{target:e," + SEL_SPREAD +
          b"},t,n.revision,n.logEpoch)}/*[zcode-editresend-ui]*/,[Ni,t])")
BI_NEW_3182 = (b"return Mi(`retryTurn`,{target:e," + SEL_SPREAD_3182 +
               b"},t,n.revision,n.logEpoch)}/*[zcode-editresend-ui]*/,[Mi,t])")

# 3.19.1: dispatcher Mi -> Di, draft reader ii -> ei (same tFn(ref,view) shape).
BI_OLD_3191 = b"return Di(`retryTurn`,{target:e},t,n.revision,n.logEpoch)},[Di,t])"
SEL_SPREAD_3191 = (b"...((_r)=>_r?{modelSelection:_r.modelSelection,"
                   b"mode:_r.mode,planEnabled:_r.planEnabled}:{})(ei())")
BI_NEW_3191 = (b"return Di(`retryTurn`,{target:e," + SEL_SPREAD_3191 +
               b"},t,n.revision,n.logEpoch)}/*[zcode-editresend-ui]*/,[Di,t])")


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


def schema_aliases(data: bytes) -> tuple:
    """Read the live (target, modelSelection, mode) aliases for the retryTurn
    widening. Both come from the SAME scope: `target` from the retryTurn schema
    that is about to be widened, modelSelection/mode from its sibling
    editUserQuery schema.

    Reading the target live (instead of trusting RT_OLD/RT_OLD_3182) is what
    closes the last hole: a future build could keep `target:DR` but revert the
    mode alias, and a hardcoded 3182 branch would then inject `J4.optional()`
    where the file says otherwise - the `Nl is not defined` class of boot
    crash, one aliasing coincidence away."""
    m = EDIT_SCHEMA_RE.search(data)
    if not m:
        fail("cjs: cannot locate editUserQuery schema to derive aliases "
             "(version drift?) - refusing to patch", 2)
    t = RETRY_TARGET_RE.search(data)
    if not t:
        fail("cjs: cannot locate retryTurn schema to derive its target alias "
             "(version drift?) - refusing to patch", 2)
    return t.group(1), m.group(1), m.group(2)


def assert_schema_aliases(aliases: tuple) -> None:
    """Fail loudly when the live aliases are not a combination this module has
    verified. Silent drift here is what produced `Nl is not defined` ->
    transport_closed -> ZCode would not boot."""
    tgt, live_ms, live_mode = aliases
    known = {
        (b"PR", b"Wc", b"H4"),   # 3.18.0
        (b"DR", b"Wc", b"J4"),   # 3.18.2
        (b"$R", b"qc", b"fj"),   # 3.19.1
    }
    if (tgt, live_ms, live_mode) not in known:
        fail(f"cjs: schema aliases drifted - live target={tgt.decode()} "
             f"modelSelection={live_ms.decode()} mode={live_mode.decode()}; "
             f"known PR/Wc/H4 (3.18.0), DR/Wc/J4 (3.18.2), $R/qc/fj (3.19.1). "
             f"Update RT_NEW* and `known` before injecting.", 2)
    log(f"cjs: schema aliases ok (target={tgt.decode()}, "
        f"modelSelection={live_ms.decode()}, mode={live_mode.decode()})")


def patch_gate(data: bytes) -> tuple:
    """Widen the canonical-intent payload gate so retryTurn contributes its
    payload too. The local variable name differs per build (`d` in 3.18.x,
    `p` in 3.19.1), so it is captured from the live text rather than assumed.

    The marker comment sits BEFORE the `let`, so a re-run must detect the
    already-widened form first; matching only the pristine shape would make the
    second install report "anchor not found"."""
    if GATE_INJECTED_RE.search(data):
        log("cjs L1: builder gate already widened, skip")
        return data, False
    m = GATE_RE.search(data)
    if not m:
        fail("cjs L1: builder-gate anchor not found (version drift?)", 2)
    var = m.group(1)
    old = b"let " + var + b'=t.type==="editUserQuery"?t.payload:void 0'
    new = (V7_TAG + b"let " + var +
           b'=t.type==="editUserQuery"||t.type==="retryTurn"?t.payload:void 0')
    n = data.count(old)
    if n != 1:
        fail(f"cjs builder-gate anchor matched {n} times (expected 1)", 2)
    log(f"cjs L1: builder payload gate now covers retryTurn (var={var.decode()})")
    return data.replace(old, new, 1), True


def patch_cjs(tpath: Path) -> None:
    data = tpath.read_bytes()
    changed = False

    aliases = schema_aliases(data)
    assert_schema_aliases(aliases)

    data, gate_changed = patch_gate(data)
    changed = gate_changed

    # Build both sides from the LIVE aliases, so the injected text can never
    # disagree with the file it lands in. The literal RT_OLD/RT_NEW constants
    # stay for uninject/verify (they have to recognise text written by an older
    # run), but inject no longer picks one by string matching.
    tgt, live_ms, live_mode = aliases
    zod = b"d" if b"editUserQuery:d.object(" in data else b"m"
    rt_old_live = (b"retryTurn:" + zod + b".object({target:" + tgt +
                   b"}),setAssistantFeedback")
    rt_new_live = (b"retryTurn:" + zod + b".object({target:" + tgt +
                   b",modelSelection:" + live_ms + b".optional(),mode:" +
                   live_mode + b".optional(),planEnabled:" + zod +
                   b".boolean().optional()}),"
                   b"setAssistantFeedback")
    if rt_new_live in data or RT_NEW in data or RT_NEW_3182 in data:
        log("cjs L2: retryTurn schema already widened, skip")
    else:
        n = data.count(rt_old_live)
        if n != 1:
            fail(f"cjs retryTurn schema anchor matched {n} times (expected 1) "
                 f"for target={tgt.decode()} (version drift?)", 2)
        data = data.replace(rt_old_live, rt_new_live, 1)
        changed = True
        log("cjs L2: retryTurn schema widened")

    if changed:
        node_check(data, "cjs")
        tpath.write_bytes(data)


def renderer_candidates(root: Path):
    assets = root / "out" / "renderer" / "assets"
    if not assets.is_dir():
        fail(f"renderer assets dir not found: {assets}")
    keys = [BI_OLD, BI_OLD_3182, BI_OLD_3191, BI_NEW, BI_NEW_3182,
            BI_NEW_3191, NEE_UPSTREAM, b"zcode-editresend-ui"]
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

    if BI_NEW in data or BI_NEW_3182 in data or BI_NEW_3191 in data:
        log("renderer: retry already carries selection, skip")
        return
    for old, new, note in ((BI_OLD, BI_NEW, "si"),
                           (BI_OLD_3182, BI_NEW_3182, "ii()"),
                           (BI_OLD_3191, BI_NEW_3191, "ei()")):
        n = data.count(old)
        if n == 1:
            data = data.replace(old, new, 1)
            log(f"renderer: retry callback now carries live draft selection ({note})")
            break
    else:
        fail("renderer retry anchor matched 0 or >1 times (expected 1) "
             "(version drift?)", 2)

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
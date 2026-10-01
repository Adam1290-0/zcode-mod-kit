#!/usr/bin/env python3
"""edit-resend-model-fix v2.1: cjs + renderer injector for zcode-mod-kit.

GOAL: "edit user query" / "retry turn" must run with the model the user has
CURRENTLY selected in the composer.

Layers (one module, two targets):

cjs (zcode.cjs):
  L1 SJo/startCanonicalIntent replays payload-priority instead of the frozen
     original modelSelection/mode/planEnabled (payload > void > current binding).
  L2 schemas accept optional modelSelection/mode/planEnabled on editUserQuery/
     retryTurn (zod strips undeclared keys otherwise).

renderer (styles-*.js chunk):
  L3 schemas widened likewise (ni registry).
  L4 the edit (nee) + retry (bi) callbacks attach the composer's CURRENT
     selection by calling Qn() live at click time (Qn = $T(Bn.current, Yn) in
     the same pane component, where Bn.current.modelSelection is the draft
     updated synchronously by handleDraftSelectModel). This replaced v2.0's
     window.__zermSel cross-component render snapshot, which could go stale
     when the composer component had not re-rendered yet after a model switch.

Version states handled idempotently (renderer): pristine / v2.0 (window.
__zermSel spread) / v2.1 (Qn() spread) all converge to v2.1.
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

SLUG = "edit-resend-model-fix"

# ----------------------------- cjs anchors ---------------------------------
STALE3 = (b"modelSelection:o.intent.modelSelection,"
          b"mode:o.intent.mode,planEnabled:o.intent.planEnabled,")
V1_COMMENT = b"/*[zcode-editresend-model-fix]*/"
V2_TAG = b"/*[zcode-editresend-model-fix:v2]*/"
FINAL_SJO = (V2_TAG
             + b"modelSelection:n.payload?.modelSelection,"
             b"mode:n.payload?.mode,"
             b"planEnabled:n.payload?.planEnabled!==void 0?"
             b"n.payload.planEnabled:void 0,")
CJS_SCHEMA_OLD = (b"editUserQuery:m.object({target:NR,newText:m.string(),"
                  b"attachments:m.array(Mpe).optional(),"
                  b'workspaceMode:m.enum(["preserve","rewind"]).optional()}),'
                  b"retryTurn:m.object({target:NR})")
CJS_SCHEMA_NEW = (b"editUserQuery:m.object({target:NR,newText:m.string(),"
                  b"attachments:m.array(Mpe).optional(),"
                  b'workspaceMode:m.enum(["preserve","rewind"]).optional(),'
                  b"modelSelection:Pu.optional(),mode:Npe.optional(),"
                  b"planEnabled:m.boolean().optional()}),"
                  b"retryTurn:m.object({target:NR,modelSelection:Pu.optional(),"
                  b"mode:Npe.optional(),planEnabled:m.boolean().optional()})")

# --------------------------- renderer anchors ------------------------------
RS_SCHEMA_OLD = (b"editUserQuery:ni({target:Ni,newText:h(),"
                 b"attachments:Be(Va).optional(),"
                 b"workspaceMode:Gr([`preserve`,`rewind`]).optional()}),"
                 b"retryTurn:ni({target:Ni})")
RS_SCHEMA_NEW = (b"editUserQuery:ni({target:Ni,newText:h(),"
                 b"attachments:Be(Va).optional(),"
                 b"workspaceMode:Gr([`preserve`,`rewind`]).optional(),"
                 b"modelSelection:va.optional(),mode:Na.optional(),"
                 b"planEnabled:Ot().optional()}),"
                 b"retryTurn:ni({target:Ni,modelSelection:va.optional(),"
                 b"mode:Na.optional(),planEnabled:Ot().optional()})")

# stash: keeps window.__zermSel write (harmless; v2.1 reads Qn() instead).
R_STASH_ANCHOR = b"}),[y.mode,y.planEnabled,w]),E=(0,Q.useRef)(T);"
R_STASH_INSERT = (b"}),[y.mode,y.planEnabled,w]),E=(0,Q.useRef)(T);"
                  b"window.__zermSel={mode:y.mode,planEnabled:"
                  b'y.planEnabled??!1,modelSelection:w};'
                  b"/*[zcode-editresend-ui]*/")

# v2.0 spread (stale render snapshot), v2.1 spread (stale Qn() closure),
# v2.2 spread (live Bn.current ref - the draft config, updated synchronously).
WM = (b"...window.__zermSel?{modelSelection:window.__zermSel."
      b"modelSelection,mode:window.__zermSel.mode,"
      b"planEnabled:window.__zermSel.planEnabled}:{}")
QN = (b"...(Qn()?{modelSelection:Qn().modelSelection,mode:Qn().mode,"
      b"planEnabled:Qn().planEnabled}:{})")
BN = (b"...(Bn.current.modelSelection?{modelSelection:Bn.current."
      b"modelSelection,mode:Bn.current.mode,"
      b"planEnabled:Bn.current.planEnabled}:{})")

NEE_PRISTINE = (b"let o=await br(`editUserQuery`,{target:e,newText:n,"
                b"workspaceMode:i,...r?{attachments:[...r]}:{}},t,a.revision,"
                b"a.logEpoch);")
NEE_PATCHED = (b"let o=await br(`editUserQuery`,{target:e,newText:n,"
               b"workspaceMode:i," + BN +
               b",...r?{attachments:[...r]}:{}},t,a.revision,"
               b"a.logEpoch);/*[zcode-editresend-ui]*/")
NEE_V21 = (b"let o=await br(`editUserQuery`,{target:e,newText:n,"
           b"workspaceMode:i," + QN +
           b",...r?{attachments:[...r]}:{}},t,a.revision,"
           b"a.logEpoch);/*[zcode-editresend-ui]*/")
NEE_V20 = (b"let o=await br(`editUserQuery`,{target:e,newText:n,"
           b"workspaceMode:i," + WM +
           b",...r?{attachments:[...r]}:{}},t,a.revision,"
           b"a.logEpoch);/*[zcode-editresend-ui]*/")
BI_PRISTINE = b"return br(`retryTurn`,{target:e},t,n.revision,n.logEpoch)"
BI_PATCHED = (b"return br(`retryTurn`,{target:e," + BN +
              b"}/*[zcode-editresend-ui]*/,t,n.revision,n.logEpoch)")
BI_V21 = (b"return br(`retryTurn`,{target:e," + QN +
          b"}/*[zcode-editresend-ui]*/,t,n.revision,n.logEpoch)")
BI_V20 = (b"return br(`retryTurn`,{target:e," + WM +
          b"}/*[zcode-editresend-ui]*/,t,n.revision,n.logEpoch)")

MARKER_UI = b"zcode-editresend-ui"


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

    has_final = b"zcode-editresend-model-fix:v2" in data
    has_v1 = V1_COMMENT in data
    has_stale = STALE3 in data

    if has_final and not has_v1 and not has_stale:
        log("cjs: SJo replay already v2, skip")
    elif has_v1:
        n = data.count(V1_COMMENT)
        if n != 1:
            fail(f"cjs v1 comment matched {n} times (expected 1)", 2)
        data = data.replace(V1_COMMENT, FINAL_SJO, 1)
        log("cjs L1: upgraded v1 strip -> payload-priority replay (v2)")
    elif has_stale:
        n = data.count(STALE3)
        if n != 1:
            fail(f"cjs stale-fields anchor matched {n} times (expected 1)", 2)
        data = data.replace(STALE3, FINAL_SJO, 1)
        log("cjs L1: stripped stale fields -> payload-priority replay (v2)")
    else:
        fail("cjs: neither pristine anchor nor previous markers found "
             "(version drift?)", 2)

    if CJS_SCHEMA_NEW in data:
        log("cjs L2: schema already widened, skip")
    else:
        n = data.count(CJS_SCHEMA_OLD)
        if n != 1:
            fail(f"cjs schema anchor matched {n} times (expected 1)", 2)
        data = data.replace(CJS_SCHEMA_OLD, CJS_SCHEMA_NEW, 1)
        log("cjs L2: widened editUserQuery/retryTurn schemas (cjs side)")

    node_check(data, "cjs")
    tpath.write_bytes(data)


def renderer_candidates(root: Path):
    assets = root / "out" / "renderer" / "assets"
    if not assets.is_dir():
        fail(f"renderer assets dir not found: {assets}")
    keys = [R_STASH_ANCHOR, RS_SCHEMA_OLD, RS_SCHEMA_NEW, WM, QN, BN,
            NEE_PRISTINE, BI_PRISTINE, MARKER_UI]
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

    # unit 1: stash (harmless; v2.2 reads the live ref, not the snapshot)
    if b"window.__zermSel={mode:y.mode" in data:
        pass
    else:
        n = data.count(R_STASH_ANCHOR)
        if n != 1:
            fail(f"renderer stash anchor matched {n} times (expected 1)", 2)
        data = data.replace(R_STASH_ANCHOR, R_STASH_INSERT, 1)
        changed = True
        log("renderer stash: applied")

    # unit 2: schema widening
    if RS_SCHEMA_NEW in data:
        pass
    else:
        n = data.count(RS_SCHEMA_OLD)
        if n != 1:
            fail(f"renderer schema anchor matched {n} times (expected 1)", 2)
        data = data.replace(RS_SCHEMA_OLD, RS_SCHEMA_NEW, 1)
        changed = True
        log("renderer rs-schema: applied")

    # unit 3: nee/bi read the live draft ref Bn.current (v2.2).
    # Upgrade any previously-injected variant (v2.0 window.__zermSel snapshot
    # / v2.1 Qn() stale closure) whose spread is WM or QN, in both the nee
    # and bi call sites.
    if BN in data:
        log("renderer nee/bi: already Bn.current (v2.2)")
    elif WM in data or QN in data:
        bad = WM if WM in data else QN
        n = data.count(bad)
        if n != 2:
            fail(f"renderer {len(bad)}-byte spread matched {n} times "
                 "(expected 2)", 2)
        data = data.replace(bad, BN)
        changed = True
        log("renderer nee/bi: upgraded legacy spread -> Bn.current (v2.2)")
    elif NEE_PRISTINE in data and BI_PRISTINE in data:
        if data.count(NEE_PRISTINE) != 1 or data.count(BI_PRISTINE) != 1:
            fail("renderer pristine anchors not unique; abort", 2)
        data = data.replace(NEE_PRISTINE, NEE_PATCHED, 1)
        data = data.replace(BI_PRISTINE, BI_PATCHED, 1)
        changed = True
        log("renderer nee/bi: pristine -> Bn.current (v2.2)")
    else:
        fail("renderer nee/bi: no recognizable state; abort", 2)

    if not changed:
        log("renderer: already injected, skip")
        return
    node_check(data, "renderer")
    rpath.write_bytes(data)


def main() -> None:
    ap = argparse.ArgumentParser(description=f"{SLUG}: inject v2.1 fix")
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
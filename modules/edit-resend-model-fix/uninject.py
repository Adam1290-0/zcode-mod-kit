#!/usr/bin/env python3
"""edit-resend-model-fix v2.1: cjs + renderer uninjector for zcode-mod-kit.

Reverses v2.1 (and v2.0) back to the OFFICIAL pristine state on both targets,
byte-exactly.
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

SLUG = "edit-resend-model-fix"

STALE3 = (b"modelSelection:o.intent.modelSelection,"
          b"mode:o.intent.mode,planEnabled:o.intent.planEnabled,")
V1_COMMENT = b"/*[zcode-editresend-model-fix]*/"
FINAL_SJO = (b"/*[zcode-editresend-model-fix:v2]*/"
             b"modelSelection:n.payload?.modelSelection,"
             b"mode:n.payload?.mode,"
             b"planEnabled:n.payload?.planEnabled!==void 0?"
             b"n.payload.planEnabled:void 0,")
CJS_SCHEMA_NEW = (b"editUserQuery:m.object({target:NR,newText:m.string(),"
                  b"attachments:m.array(Mpe).optional(),"
                  b'workspaceMode:m.enum(["preserve","rewind"]).optional(),'
                  b"modelSelection:Pu.optional(),mode:Npe.optional(),"
                  b"planEnabled:m.boolean().optional()}),"
                  b"retryTurn:m.object({target:NR,modelSelection:Pu.optional(),"
                  b"mode:Npe.optional(),planEnabled:m.boolean().optional()})")
CJS_SCHEMA_OLD = (b"editUserQuery:m.object({target:NR,newText:m.string(),"
                  b"attachments:m.array(Mpe).optional(),"
                  b'workspaceMode:m.enum(["preserve","rewind"]).optional()}),'
                  b"retryTurn:m.object({target:NR})")

RS_SCHEMA_NEW = (b"editUserQuery:ni({target:Ni,newText:h(),"
                 b"attachments:Be(Va).optional(),"
                 b"workspaceMode:Gr([`preserve`,`rewind`]).optional(),"
                 b"modelSelection:va.optional(),mode:Na.optional(),"
                 b"planEnabled:Ot().optional()}),"
                 b"retryTurn:ni({target:Ni,modelSelection:va.optional(),"
                 b"mode:Na.optional(),planEnabled:Ot().optional()})")
RS_SCHEMA_OLD = (b"editUserQuery:ni({target:Ni,newText:h(),"
                 b"attachments:Be(Va).optional(),"
                 b"workspaceMode:Gr([`preserve`,`rewind`]).optional()}),"
                 b"retryTurn:ni({target:Ni})")

R_STASH_FINAL = (b"}),[y.mode,y.planEnabled,w]),E=(0,Q.useRef)(T);"
                 b"window.__zermSel={mode:y.mode,planEnabled:"
                 b'y.planEnabled??!1,modelSelection:w};'
                 b"/*[zcode-editresend-ui]*/")
R_STASH_ORIG = b"}),[y.mode,y.planEnabled,w]),E=(0,Q.useRef)(T);"

WM = (b"...window.__zermSel?{modelSelection:window.__zermSel."
      b"modelSelection,mode:window.__zermSel.mode,"
      b"planEnabled:window.__zermSel.planEnabled}:{}")
QN = (b"...(Qn()?{modelSelection:Qn().modelSelection,mode:Qn().mode,"
      b"planEnabled:Qn().planEnabled}:{})")
BN = (b"...(Bn.current.modelSelection?{modelSelection:Bn.current."
      b"modelSelection,mode:Bn.current.mode,"
      b"planEnabled:Bn.current.planEnabled}:{})")


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

    if FINAL_SJO in data:
        n = data.count(FINAL_SJO)
        if n != 1:
            fail(f"cjs v2 replay matched {n} times (expected 1)", 2)
        data = data.replace(FINAL_SJO, STALE3, 1)
        touched = True
        log("cjs: v2 replay restored to official fields")
    elif V1_COMMENT in data:
        n = data.count(V1_COMMENT)
        if n != 1:
            fail(f"cjs v1 comment matched {n} times (expected 1)", 2)
        data = data.replace(V1_COMMENT, STALE3, 1)
        touched = True
        log("cjs: v1 strip restored to official fields")
    elif STALE3 in data:
        log("cjs: no SJo patch present")

    if CJS_SCHEMA_NEW in data:
        n = data.count(CJS_SCHEMA_NEW)
        if n != 1:
            fail(f"cjs widened schema matched {n} times (expected 1)", 2)
        data = data.replace(CJS_SCHEMA_NEW, CJS_SCHEMA_OLD, 1)
        touched = True
        log("cjs: schema unwidened")

    if touched:
        node_check(data, "cjs")
        tpath.write_bytes(data)
        log("cjs uninjected")


def renderer_candidates(root: Path):
    assets = root / "out" / "renderer" / "assets"
    if not assets.is_dir():
        fail(f"renderer assets dir not found: {assets}")
    keys = [b"zcode-editresend-ui", BN, QN, WM, R_STASH_FINAL, RS_SCHEMA_NEW,
            RS_SCHEMA_OLD]
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

    # stash
    if R_STASH_FINAL in data:
        if data.count(R_STASH_FINAL) != 1:
            fail("renderer stash matched != 1; abort", 2)
        data = data.replace(R_STASH_FINAL, R_STASH_ORIG, 1)
        touched = True
        log("renderer stash: reverted")
    elif R_STASH_ORIG in data:
        log("renderer stash: already official")

    # rs-schema
    if RS_SCHEMA_NEW in data:
        if data.count(RS_SCHEMA_NEW) != 1:
            fail("renderer schema matched != 1; abort", 2)
        data = data.replace(RS_SCHEMA_NEW, RS_SCHEMA_OLD, 1)
        touched = True
        log("renderer rs-schema: reverted")

    # nee/bi model read spread (v2.0/v2.1/v2.2) -> pristine.
    # All variants share the identical surrounding call text; only the inner
    # "..." spread differs. Rebuild the pristine call from whichever variant
    # is present by replacing the whole injected spread token.
    spread = None
    for cand in (BN, QN, WM):
        if cand in data:
            if data.count(cand) != 2:
                fail(f"renderer spread matched {data.count(cand)} times "
                     "(expected 2)", 2)
            spread = cand
            break
    if spread is not None:
        data = data.replace(
            b"workspaceMode:i," + spread + b",...r?{attachments:[...r]}:{}}"
            b",t,a.revision,a.logEpoch);/*[zcode-editresend-ui]*/",
            b"workspaceMode:i,...r?{attachments:[...r]}:{}},t,a.revision,"
            b"a.logEpoch);", 1)
        data = data.replace(
            b"br(`retryTurn`,{target:e," + spread +
            b"}/*[zcode-editresend-ui]*/,t,n.revision,n.logEpoch)",
            b"br(`retryTurn`,{target:e},t,n.revision,n.logEpoch)", 1)
        touched = True
        log("renderer nee/bi: reverted to pristine")

    if b"/*[zcode-editresend-ui]*/" in data or WM in data or QN in data \
            or BN in data:
        fail("renderer: stray editresend markers remain; abort", 2)

    if touched:
        node_check(data, "renderer")
        rpath.write_bytes(data)
        log("renderer uninjected")


def main() -> None:
    ap = argparse.ArgumentParser(description=f"{SLUG}: un-inject v2.1 fix")
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
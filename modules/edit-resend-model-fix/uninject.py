#!/usr/bin/env python3
"""edit-resend-model-fix v7: cjs + renderer uninjector for zcode-mod-kit.

Reverses v7 back to the OFFICIAL upstream state, byte-exactly, on both targets.
The edit path is untouched by v7 (fixed upstream), so only the retry-side
patches are reverted.

Every patch this module writes is located by pattern, not by a single
version's minified names: the gate variable, the zod binding, the schema
aliases, the renderer dispatcher and the draft reader all vary per build.
"""
import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SLUG = "edit-resend-model-fix"

GATE_WIDENED_RE = re.compile(
    rb'/\*\[zcode-editresend-model-fix:v7\]\*/let ([\w$]+)=t\.type==="'
    rb'editUserQuery"\|\|t\.type==="retryTurn"\?t\.payload:void 0')

# Matches the widened retryTurn schema TOGETHER WITH the ",setAssistantFeedback"
# that follows it. The injector wrote
#   retryTurn:z.object({...planEnabled:z.boolean().optional()}),setAssistantFeedback
# so the narrow replacement must regenerate the comma AND the next key. The
# earlier version stopped at `})` and appended ",setAssistantFeedback" itself,
# leaving the original one in place -> `setAssistantFeedback,setAssistantFeedback`
# -> zcode.cjs would not restore byte-exactly (caught by uninstall verification).
RT_WIDENED_RE = re.compile(
    rb"retryTurn:([\w$]+)\.object\(\{target:([\w$]+),modelSelection:[\w$]+"
    rb"\.optional\(\),mode:[\w$]+\.optional\(\),"
    rb"planEnabled:[\w$]+\.boolean\(\)\.optional\(\)\}\)(,setAssistantFeedback)")

# The injected renderer callback, whatever dispatcher/reader it used:
#   return <D>(`retryTurn`,{target:e,<IIFE spread>},t,n.revision,n.logEpoch)}/*marker*/,[<D>,t])
BI_INJECTED_RE = re.compile(
    rb"return ([\w$]+)\(`retryTurn`,\{target:e,"
    rb"\.\.\.\(\(_r\)=>_r\?\{modelSelection:_r\.modelSelection,mode:_r\.mode,"
    rb"planEnabled:_r\.planEnabled\}:\{\}\)\([\w$]+\(\)\)"
    rb"\},t,n\.revision,n\.logEpoch\)\}"
    rb"/\*\[zcode-editresend-ui\]\*/,\[\1,t\]\)")


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

    m = GATE_WIDENED_RE.search(data)
    if m:
        var = m.group(1)
        narrowed = (b"let " + var + b'=t.type==="editUserQuery"?t.payload:void 0')
        if data.count(m.group(0)) != 1:
            fail("cjs builder gate patch matched != 1; abort", 2)
        # GATE_WIDENED_RE includes the marker comment, so this one replace
        # restores the pristine text byte-for-byte.
        data = data.replace(m.group(0), narrowed, 1)
        touched = True
        log(f"cjs L1: builder gate restored to editUserQuery-only "
            f"(var={var.decode()})")
    else:
        log("cjs L1: no patch present")

    m = RT_WIDENED_RE.search(data)
    if m:
        zod, tgt, tail = m.group(1), m.group(2), m.group(3)
        narrowed = (b"retryTurn:" + zod + b".object({target:" + tgt +
                    b"})" + tail)
        if data.count(m.group(0)) != 1:
            fail("cjs retryTurn widened schema matched != 1; abort", 2)
        data = data.replace(m.group(0), narrowed, 1)
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
    for js in sorted(assets.glob("*.js")):
        if js.stat().st_size < 100_000:
            continue
        data = js.read_bytes()
        if (b"zcode-editresend-ui" in data
                or BI_INJECTED_RE.search(data)):
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

    m = BI_INJECTED_RE.search(data)
    if m:
        d = m.group(1)
        plain = (b"return " + d + b"(`retryTurn`,{target:e},t,n.revision,"
                 b"n.logEpoch)},[" + d + b",t])")
        if data.count(m.group(0)) != 1:
            fail("renderer retry patch matched != 1; abort", 2)
        data = data.replace(m.group(0), plain, 1)
        touched = True
        log(f"renderer retry: reverted (dispatcher={d.decode()})")

    if b"zcode-editresend-ui" in data:
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
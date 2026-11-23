#!/usr/bin/env python3
"""Regression tests for the 2026-11-12 incident.

Two failures shipped together and both are covered here:

1. ZCode would not boot after patching:
       failedPhase: preparing_session_storage, errorCode: transport_closed
   The storage-prep worker spawns `zcode.cjs app-server --stdio
   --prepare-storage` and speaks newline-delimited JSON on stdout. edit-resend
   v7 widened the retryTurn schema with `modelSelection:Nl.optional()`, but `Nl`
   is not a zod schema in that scope (the real aliases are Wc / H4). The worker
   died with "Nl is not defined" before emitting storagePrepared, so the main
   process reported transport_closed.

   `node --check` cannot catch this: the file parses fine, the identifier is
   simply undefined at runtime. These tests therefore (a) assert the aliases
   used by the patch resolve inside the same schema as editUserQuery, and
   (b) when a real ZCode tree is available, actually run the storage-prep
   subprocess and require a storagePrepared reply.

2. Uninstall reported success but left <script id="zcode-skin-ui"> in app.asar.
   verify.py returned 1 for both "not injected" and "injected but stale"; the
   installer's gate reads 1 as "nothing to do" and skipped the uninject.
   Verification now returns 2 for stale, and these tests pin that contract.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODS = ROOT / "modules"


def _find_zcode_root():
    """Locate the ZCode install the same way modkit does, so these tests work on
    any machine without an env var. Returns None when ZCode is not installed."""
    env = os.environ.get("ZCODE_ROOT")
    cands = [Path(env)] if env else []
    cands += [Path(r"H:\Zcode"), Path(r"D:\ZCode"),
              Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "ZCode",
              Path(os.environ.get("PROGRAMFILES", "")) / "ZCode"]
    for c in cands:
        if str(c) and (c / "resources" / "app.asar").is_file():
            return c
    return None


_ZROOT = _find_zcode_root()
# Optional: an extracted reference tree from another ZCode version (only used
# by the renderer-fixture branch of the boot test).
FIXTURES = Path(os.environ.get("ZCODE_3180_REF",
                               str(ROOT / ".upgrade-check-ref")))
# Prefer an explicit override, then the local pristine baseline, then nothing.
CJS_BAK = Path(os.environ.get("ZCODE_CJS") or
               ((_ZROOT / "resources" / "glm" / "zcode.cjs.kitbak")
                if _ZROOT else Path("__no_zcode__")))

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name}" + (f"\n         {detail}" if detail else ""))


def run(script, args, env=None):
    p = subprocess.run([sys.executable, str(script)] + args,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _const_blocks(src):
    """Yield every `NAME = (b"..." b"...")` / `NAME = b"..."` literal in a file,
    so assertions about byte payloads never trip over prose in comments."""
    for m in re.finditer(r'^\s*([A-Z][A-Z0-9_]*)\s*=\s*(\(?)', src, re.M):
        if not m.group(2):
            line = src[m.end():src.find("\n", m.end())]
            if not line.lstrip().startswith('b"'):
                continue
            yield line
            continue
        end = src.find("\n)\n", m.end())
        if end < 0:
            continue
        yield src[m.end():end]


def test_schema_alias_resolution():
    """The v7 retryTurn widening must reuse editUserQuery's real aliases."""
    print("\n--- edit-resend: schema aliases resolve in the same scope")
    src = (MODS / "edit-resend-model-fix" / "inject.py").read_text(encoding="utf-8")
    # assert_schema_aliases() must gate on the WHOLE (target, modelSelection,
    # mode) triple. Checking modelSelection and mode separately let a future
    # build pair `target:DR` with a reverted `mode:H4` slip through, and the
    # hardcoded 3182 branch would then inject J4.optional() anyway - the same
    # boot-crash class as Nl, one aliasing coincidence away.
    check("inject.py derives the live target alias",
          "RETRY_TARGET_RE" in src and "schema_aliases(data)" in src,
          src[:200])
    check("alias guard compares target+modelSelection+mode as a triple",
          '(tgt, live_ms, live_mode) not in known' in src, src[:200])
    known = re.findall(r'\(b"([A-Za-z$][\w$]*)", b"([A-Za-z$][\w$]*)", '
                       r'b"([A-Za-z$][\w$]*)"\)', src)
    check("all verified alias triples are declared",
          ("PR", "Wc", "H4") in known and ("DR", "Wc", "J4") in known
          and ("$R", "qc", "fj") in known, str(known))
    # Only the BYTE CONSTANTS matter - the comments deliberately name Nl/Cge
    # to explain the incident.
    consts = "\n".join(_const_blocks(src))
    check("no alias constant references Nl", "Nl.optional()" not in consts,
          consts[:200])
    check("no alias constant references Cge", "Cge.optional()" not in consts,
          consts[:200])

    # uninject / verify must still recognise every payload an older run could
    # have written, or a module can be applied but never removed. Since 3.19.1
    # they match by SHAPE (regex over `target:<alias>,modelSelection:<alias>`)
    # rather than by literal alias, so assert the shape regexes instead of the
    # individual alias triples.
    for name in ("uninject.py", "verify.py"):
        txt = (MODS / "edit-resend-model-fix" / name).read_text(encoding="utf-8")
        check(f"{name} matches retry schema by shape, not literal alias",
              "target:" in txt and "modelSelection:" in txt
              and "[\\w$]+" in txt, txt[:200])
        check(f"{name} matches the spread for any reader name (si/ii/ei)",
              "modelSelection:_r" in txt and "_r" in txt, txt[:200])
        check(f"{name} has no stale Nl alias",
              "modelSelection:Nl.optional()" not in txt)

    # Idempotency: a second inject must recognise its own output. The live
    # target regex has to stop at `,` as well as `}` or it cannot see a schema
    # it already widened (regression caught on the real 3.18.2 tree).
    check("live target regex accepts an already-widened schema",
          r'[\w$]+)[,}]' in src, src[:200])

    if not CJS_BAK.is_file():
        print("  [SKIP] original cjs not available, cannot verify scope")
        return
    cjs = CJS_BAK.read_bytes().decode("utf-8", "replace")
    i = cjs.find("editUserQuery:m.object(")
    check("editUserQuery schema found in cjs", i > 0)
    if i <= 0:
        return
    seg = cjs[i:i + 520]
    aliases = {}
    for key in ("modelSelection", "mode"):
        a = re.search(key + r":([A-Za-z_$][\w$]*)", seg)
        aliases[key] = a.group(1) if a else "?"
    t = re.search(r"retryTurn:m\.object\(\{target:([A-Za-z_$][\w$]*)", cjs)
    aliases["target"] = t.group(1) if t else "?"
    triple = (aliases["target"], aliases["modelSelection"], aliases["mode"])
    check(f"this cjs's alias triple {triple} is one the module knows",
          triple in (("PR", "Wc", "H4"), ("DR", "Wc", "J4")), str(triple))
    # An alias only counts if it really behaves like a zod schema.
    check("Wc.optional() appears many times (real zod alias)",
          len(re.findall(r"\bWc\.optional\(\)", cjs)) > 10)
    check("Nl is NOT a zod schema (the original bug)",
          len(re.findall(r"\bNl\.optional\(\)", cjs)) == 0)


def _zcode_exe():
    if _ZROOT is not None:
        exe = _ZROOT / "ZCode.exe"
        if exe.is_file():
            return exe
    return None


def _extract_renderer_refs(dest):
    """Pull out/renderer/index.html + every assets/*.js out of the local
    app.asar by reading the index, so tests need no staged fixture tree.
    Returns None when ZCode is absent (the caller then skips the renderer
    half rather than failing)."""
    if _ZROOT is None:
        return None
    asar = _ZROOT / "resources" / "app.asar"
    if not asar.is_file():
        return None
    import struct
    try:
        with open(asar, "rb") as f:
            f.seek(4)
            jl = struct.unpack("<I", f.read(4))[0]
            hdr = f.read(jl).decode("utf-8", "replace")
        pkg = json.loads(hdr[hdr.find("{"):].rstrip("\0"))
        base = 8 + jl
        base += (4 - (base % 4)) % 4
        root = dest / "_refs"
        (root / "out" / "renderer" / "assets").mkdir(parents=True, exist_ok=True)

        def grab(node, parts, out_path):
            for name, e in node.get("files", {}).items():
                p = parts + [name]
                if "files" in e:
                    grab(e, p, out_path)
                elif "offset" in e:
                    with open(asar, "rb") as f:
                        f.seek(base + int(e["offset"]))
                        data = f.read(int(e["size"]))
                    tgt = out_path.joinpath(*p)
                    tgt.parent.mkdir(parents=True, exist_ok=True)
                    tgt.write_bytes(data)

        rend = pkg.get("files", {}).get("out", {}).get("files", {}).get(
            "renderer", {}).get("files", {})
        for key in ("index.html", "assets"):
            if key in rend:
                grab({"files": {key: rend[key]}}, [], root / "out" / "renderer")
        return root
    except Exception:
        return None


def test_storage_prepare_runs():
    """End-to-end: patched cjs must still answer the storage-prep handshake."""
    print("\n--- boot path: storage-prep worker survives the patch")
    exe, bak = _zcode_exe(), CJS_BAK
    if not exe or not bak.is_file():
        print("  [SKIP] no ZCode executable / original cjs on this machine")
        return
    tmp = Path(tempfile.mkdtemp(prefix="zmodboot_"))
    try:
        work = tmp / "tree"
        (work / "out" / "renderer").mkdir(parents=True)
        cjs = work / "zcode.cjs"
        shutil.copy(bak, cjs)
        # The renderer half needs a chunk carrying the edit-resend anchors.
        # Prefer an explicit reference tree (ZCODE_3180_REF); otherwise pull the
        # pristine one straight out of the local ZCode install so this test
        # needs no extra fixture checked in or staged by hand.
        fixtures = FIXTURES
        if not (fixtures / "out" / "renderer" / "assets").is_dir():
            fixtures = _extract_renderer_refs(tmp)
        if fixtures and (fixtures / "out" / "renderer" / "assets").is_dir():
            shutil.copytree(fixtures / "out" / "renderer" / "assets",
                            work / "out" / "renderer" / "assets")
            shutil.copy(fixtures / "out" / "renderer" / "index.html",
                        work / "out" / "renderer" / "index.html")

        env = dict(os.environ)
        env["USERPROFILE"] = str(tmp / "home")
        env["HOME"] = str(tmp / "home")
        (tmp / "home").mkdir()
        rc, out = run(MODS / "edit-resend-model-fix" / "inject.py",
                      ["--dir", str(work), "--zcode-cjs", str(cjs)], env)
        check("edit-resend injects cleanly into a fresh cjs", rc == 0, out[-400:])

        payload = b'{"method":"startup/storagePathReady","reuse":true}\n'
        run_env = dict(os.environ)
        run_env["ELECTRON_RUN_AS_NODE"] = "1"
        try:
            p = subprocess.run(
                [str(exe), str(cjs), "app-server", "--stdio",
                 "--prepare-storage", "--cwd", str(ROOT)],
                input=payload, capture_output=True, timeout=90, env=run_env)
            reply = (p.stdout or b"").decode("utf-8", "replace")
        except subprocess.TimeoutExpired as e:
            reply = (e.stdout or b"").decode("utf-8", "replace")

        check("worker emits startup/storagePath", "startup/storagePath" in reply,
              reply[:400])
        check("worker emits startup/storagePrepared (handshake completes)",
              "startup/storagePrepared" in reply, reply[:400])
        check("worker does not die on an undefined identifier",
              "is not defined" not in reply, reply[:400])

        rc, out = run(MODS / "edit-resend-model-fix" / "uninject.py",
                      ["--dir", str(work), "--zcode-cjs", str(cjs)], env)
        check("uninject removes the v7 patch", rc == 0, out[-300:])
        check("cjs restored byte-for-byte after uninject",
              cjs.read_bytes() == bak.read_bytes())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_stale_means_injected():
    """verify must return 2 (not 1) when the payload is present but outdated."""
    print("\n--- stale payload is 'injected', never 'absent'")
    if not FIXTURES.is_dir():
        print("  [SKIP] no 3.18.0 tree available")
        return
    tmp = Path(tempfile.mkdtemp(prefix="zmodstale_"))
    try:
        work = tmp / "tree"
        (work / "out" / "renderer").mkdir(parents=True)
        shutil.copy(FIXTURES / "out" / "renderer" / "index.html",
                    work / "out" / "renderer" / "index.html")
        shutil.copytree(FIXTURES / "out" / "renderer" / "assets",
                        work / "out" / "renderer" / "assets")
        env = dict(os.environ)
        env["USERPROFILE"] = str(tmp / "home")
        env["HOME"] = str(tmp / "home")
        (tmp / "home").mkdir()

        v = MODS / "skin-manager" / "verify.py"
        rc, out = run(v, ["--dir", str(work), "--kit-version", "1.7.0"], env)
        check("absent block -> exit 1", rc == 1, f"rc={rc}")

        rc, out = run(MODS / "skin-manager" / "inject.py",
                      ["--dir", str(work), "--kit-version", "1.7.0"], env)
        check("skin-manager injects", rc == 0, out[-300:])
        rc, out = run(v, ["--dir", str(work), "--kit-version", "1.7.0"], env)
        check("fresh block -> exit 0", rc == 0, f"rc={rc}")

        # A different kit-version makes the block look outdated.
        rc, out = run(v, ["--dir", str(work), "--kit-version", "9.9.9"], env)
        check("stale block -> exit 2 (this is the uninstall bug)", rc == 2,
              f"rc={rc} {out[-300:]}")
        check("stale is reported as STALE, not FAIL", "STALE" in out, out[-300:])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_script_arg_contract():
    """Every module script must accept exactly the args modkit passes.

    modkit builds one argument list and reuses it for inject / verify /
    uninject. skin-manager's uninject.py declared no --kit-version, so argparse
    aborted with "unrecognized arguments" before the removal ran: the installer
    printed [skin-manager] FAILED and left the block in app.asar. Nothing
    checked this contract, so it went unnoticed until a user hit it.
    """
    print("\n--- argument contract: modkit's argv must not crash any script")
    mods = load_modules_for_contract()
    if not mods:
        print("  [SKIP] could not load module list")
        return
    for mod in mods:
        slug = mod["slug"]
        args = ["--dir", os.path.join(tempfile.gettempdir(), "no_such_dir_modkit")]
        if "zcode-cjs" in mod.get("targets", []):
            args += ["--zcode-cjs", os.path.join(tempfile.gettempdir(), "nope.cjs")]
        if slug == "skin-manager":
            args += ["--kit-version", "9.9.9"]
        rejects = []
        for script in ("inject.py", "verify.py", "uninject.py"):
            p = MODS / slug / script
            if not p.is_file():
                rejects.append(f"{script} missing")
                continue
            rc, out = run(p, args)
            if "unrecognized arguments" in out:
                rejects.append(script)
        check(f"{slug}: accepts modkit's argv", not rejects, ", ".join(rejects))


def load_modules_for_contract():
    """Read module.json files directly - importing modkit would run its CLI."""
    out = []
    for d in sorted(MODS.iterdir()):
        mj = d / "module.json"
        if mj.is_file():
            try:
                out.append(json.loads(mj.read_text(encoding="utf-8")))
            except Exception:
                pass
    return out


def test_edit_resend_idempotent_on_real_cjs():
    """A second inject must be a clean no-op on a real cjs, and the payload it
    writes must use THAT file's live aliases.

    The 2026-11-16 refactor derived the target alias with a regex that only
    accepted `target:X}` - so the already-widened `target:X,modelSelection:...`
    looked like "no retryTurn schema at all", and running install.bat twice (or
    reinstalling over a patched tree) aborted with exit 2."""
    print("\n--- edit-resend: re-inject is idempotent on a real cjs")
    if not CJS_BAK.is_file():
        print("  [SKIP] original cjs not available")
        return
    tmp = Path(tempfile.mkdtemp(prefix="zmodidem_"))
    try:
        cjs = tmp / "zcode.cjs"
        shutil.copy(CJS_BAK, cjs)
        env = dict(os.environ)
        env["USERPROFILE"] = str(tmp / "home")
        (tmp / "home").mkdir()

        inject = MODS / "edit-resend-model-fix" / "inject.py"
        rc1, out1 = run(inject, ["--zcode-cjs", str(cjs)], env)
        check("first inject succeeds", rc1 == 0, out1[-300:])
        once = cjs.read_bytes()

        rc2, out2 = run(inject, ["--zcode-cjs", str(cjs)], env)
        check("second inject exits 0 (no drift abort)", rc2 == 0, out2[-400:])
        check("second inject leaves the file untouched",
              cjs.read_bytes() == once)
        check("second inject reports it skipped, not re-patched",
              "already widened" in out2, out2[-300:])

        rc3, out3 = run(MODS / "edit-resend-model-fix" / "verify.py",
                        ["--zcode-cjs", str(cjs)], env)
        check("verify accepts the twice-injected file", rc3 == 0, out3[-300:])

        rc4, out4 = run(MODS / "edit-resend-model-fix" / "uninject.py",
                        ["--zcode-cjs", str(cjs)], env)
        check("uninject succeeds after a double inject", rc4 == 0, out4[-300:])
        check("cjs restored byte-for-byte", cjs.read_bytes() == CJS_BAK.read_bytes())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_schema_alias_drift_is_rejected():
    """A live triple outside the verified set must abort BEFORE writing.

    The guard used to check modelSelection and mode separately, so a build that
    kept `target:DR` but reverted `mode` to `H4` passed the check while the
    hardcoded 3182 branch still injected `J4.optional()` - the Nl class of boot
    crash by a different route."""
    print("\n--- edit-resend: unverified alias triples are refused")
    if not CJS_BAK.is_file():
        print("  [SKIP] original cjs not available")
        return
    tmp = Path(tempfile.mkdtemp(prefix="zmoddrift_"))
    try:
        env = dict(os.environ)
        env["USERPROFILE"] = str(tmp / "home")
        (tmp / "home").mkdir()
        base = CJS_BAK.read_bytes()

        # target=DR but mode reverted to H4: neither known triple
        drifted = base.replace(
            b"mode:J4.optional(),planEnabled:m.boolean().optional()}).superRefine",
            b"mode:H4.optional(),planEnabled:m.boolean().optional()}).superRefine", 1)
        if drifted == base:
            print("  [SKIP] this cjs has no DR/J4 schema to perturb")
            return
        cjs = tmp / "drift.cjs"
        cjs.write_bytes(drifted)
        rc, out = run(MODS / "edit-resend-model-fix" / "inject.py",
                      ["--zcode-cjs", str(cjs)], env)
        check("mismatched target/mode combination exits 2", rc == 2, out[-300:])
        check("the refusal names the live triple", "target=DR" in out, out[-300:])
        check("the file is left untouched", cjs.read_bytes() == drifted)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    print("=" * 62)
    print("  incident regression: boot failure + skipped uninstall")
    print("=" * 62)
    test_schema_alias_resolution()
    test_edit_resend_idempotent_on_real_cjs()
    test_schema_alias_drift_is_rejected()
    test_storage_prepare_runs()
    test_stale_means_injected()
    test_script_arg_contract()
    print("\n" + "=" * 62)
    print(f"===== {passed} passed, {failed} failed =====")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

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
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODS = ROOT / "modules"
FIXTURES = Path(os.environ.get("ZCODE_3180_REF", r"G:\工作\测试\asar_3.18.0_ref"))
CJS_BAK = Path(os.environ.get(
    "ZCODE_CJS", r"H:\Zcode\resources\glm\zcode.cjs.kitbak"))

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


def test_schema_alias_resolution():
    """The v7 retryTurn widening must reuse editUserQuery's real aliases."""
    print("\n--- edit-resend: schema aliases resolve in the same scope")
    src = (MODS / "edit-resend-model-fix" / "inject.py").read_text(encoding="utf-8")
    m = re.search(r"RT_NEW = \((.*?)\)\n", src, re.S)
    check("inject.py defines RT_NEW", m is not None)
    if not m:
        return
    blk = m.group(1)
    check("RT_NEW uses modelSelection:Wc.optional()",
          "modelSelection:Wc.optional()" in blk, blk[:200])
    check("RT_NEW uses mode:H4.optional()",
          "mode:H4.optional()" in blk, blk[:200])
    check("RT_NEW no longer references Nl",
          "Nl." not in blk, blk[:200])
    check("RT_NEW no longer references Cge",
          "Cge." not in blk, blk[:200])

    # uninject / verify must match byte-for-byte, or the module can be applied
    # but never removed.
    for name in ("uninject.py", "verify.py"):
        txt = (MODS / "edit-resend-model-fix" / name).read_text(encoding="utf-8")
        check(f"{name} agrees on modelSelection:Wc", "modelSelection:Wc.optional()" in txt)
        check(f"{name} agrees on mode:H4", "mode:H4.optional()" in txt)
        check(f"{name} has no stale Nl alias",
              "modelSelection:Nl.optional()" not in txt)

    if not CJS_BAK.is_file():
        print("  [SKIP] original cjs not available, cannot verify scope")
        return
    cjs = CJS_BAK.read_bytes().decode("utf-8", "replace")
    i = cjs.find("editUserQuery:m.object(")
    check("editUserQuery schema found in cjs", i > 0)
    if i <= 0:
        return
    seg = cjs[i:i + 520]
    for key in ("modelSelection", "mode"):
        a = re.search(key + r":([A-Za-z_$][\w$]*)", seg)
        alias = a.group(1) if a else "?"
        check(f"editUserQuery uses {key}:{alias} (matches our patch)",
              alias in ("Wc", "H4"), f"got {alias}")
    # An alias only counts if it really behaves like a zod schema.
    check("Wc.optional() appears many times (real zod alias)",
          len(re.findall(r"\bWc\.optional\(\)", cjs)) > 10)
    check("Nl is NOT a zod schema (the original bug)",
          len(re.findall(r"\bNl\.optional\(\)", cjs)) == 0)


def _zcode_exe():
    for p in (Path(r"H:\Zcode\ZCode.exe"),
              Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/ZCode/ZCode.exe"):
        if p.is_file():
            return p
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
        if FIXTURES.is_dir():
            shutil.copytree(FIXTURES / "out" / "renderer" / "assets",
                            work / "out" / "renderer" / "assets")
            shutil.copy(FIXTURES / "out" / "renderer" / "index.html",
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


def main():
    print("=" * 62)
    print("  incident regression: boot failure + skipped uninstall")
    print("=" * 62)
    test_schema_alias_resolution()
    test_storage_prepare_runs()
    test_stale_means_injected()
    print("\n" + "=" * 62)
    print(f"===== {passed} passed, {failed} failed =====")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

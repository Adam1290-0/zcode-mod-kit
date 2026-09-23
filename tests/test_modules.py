#!/usr/bin/env python3
"""Mock round-trip tests for the 5 mod-kit modules.

Builds a fake extracted-asar tree + fake zcode.cjs, runs each module's
inject -> verify -> uninject cycle and asserts byte-identical restoration.
Isolates USERPROFILE so pin/route-override runtime dirs go to a temp home.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
MODULES = KIT / "modules"

MOCK_HTML = ("<!doctype html><html><head><title>t</title></head>"
             "<body><div id=root></div></body></html>\n")
MOCK_MAIN_LF = '"use strict";\nfunction boot(){console.log(1)}\n'
MOCK_MAIN_CRLF = '"use strict";\r\nfunction boot(){console.log(1)}\r\n'
MOCK_CJS = b'#!/usr/bin/env node\n"use strict";\nconsole.log("boot");\n'
MOCK_HOST = (
    '"use strict";\n'
    "class Foo {\n"
    "  async captureBeforePromptUnsafe(t){t.signal?.throwIfAborted();"
    "let r=await this.tokenProvider();return 1;}\n"
    "  async flushActiveUpload(t){let r=await this.stateRepo.read(t),"
    "o=r.activeUpload??r.pendingUpload;return o;}\n"
    "}\n"
    "function x(){;a(pIe,\"removeGeneratedArtifactFiles\");"
    "var Bk=class{static{a(this,\"RepoSnapshotSidecarService\")}\n"
    "  }\n"
    "}\n"
)
LEGACY_RO_LINE = (b'try{require("C:/old/zcode-route-override/wrapper.js")}'
                  b'catch(e){}/*zro*/')
LEGACY_PIN_LINE = (b'try{require("C:/old/pin/pin-wrapper.js")}'
                   b'catch(e){}/*zpin*/')

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


def run(script, args, env):
    proc = subprocess.run([sys.executable, str(script)] + args,
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env)
    return proc.returncode, proc.stdout + proc.stderr


def make_tree(root: Path, html=MOCK_HTML, main=MOCK_MAIN_LF, cjs=MOCK_CJS,
              host=MOCK_HOST):
    (root / "out" / "renderer").mkdir(parents=True)
    (root / "out" / "main").mkdir(parents=True)
    (root / "out" / "host").mkdir(parents=True)
    (root / "out" / "renderer" / "index.html").write_text(html, encoding="utf-8", newline="")
    (root / "out" / "main" / "index.js").write_text(main, encoding="utf-8", newline="")
    (root / "out" / "host" / "index.js").write_text(host, encoding="utf-8", newline="")
    cjs_p = root.parent / "zcode.cjs"
    cjs_p.write_bytes(cjs)
    return cjs_p


def module(slug):
    return MODULES / slug


def cycle(name, slug, work, cjs_path, extra_env=None, inject_extra=None):
    """inject -> verify(0) -> uninject -> byte-identical, for one module."""
    env = dict(os.environ)
    env["USERPROFILE"] = str(work.parent / "home")
    env["HOME"] = str(work.parent / "home")
    if extra_env:
        env.update(extra_env)
    script = module(slug)
    args_in = ["--dir", str(work)]
    if cjs_path and "zcode-cjs" in json_get(slug, "targets"):
        args_in += ["--zcode-cjs", str(cjs_path)]
    if inject_extra:
        args_in += inject_extra

    snap = {}
    for p in work.rglob("*"):
        if p.is_file():
            snap[p] = p.read_bytes()
    if cjs_path:
        snap[cjs_path] = cjs_path.read_bytes()

    rc, out = run(script / "inject.py", args_in, env)
    check(f"{name}: inject exit 0", rc == 0, out[-400:])
    rc2, _ = run(script / "verify.py", args_in, env)
    check(f"{name}: verify exit 0 after inject", rc2 == 0)

    # idempotent re-inject while already injected prints SKIP
    rc4, out4 = run(script / "inject.py", args_in, env)
    check(f"{name}: re-inject idempotent ([SKIP] or ok)",
          rc4 == 0 and ("[SKIP]" in out4 or "skip" in out4.lower()), out4[-300:])

    rc3, out3 = run(script / "uninject.py", args_in, env)
    check(f"{name}: uninject exit 0", rc3 == 0, out3[-400:])

    # byte-identical restoration
    bad = []
    for p in snap:
        if p.exists() and p.read_bytes() != snap[p]:
            bad.append(str(p))
        elif not p.exists():
            bad.append(str(p) + " (deleted)")
    check(f"{name}: byte-identical restore", not bad, "; ".join(bad[:3]))


def json_get(slug, key):
    import json
    return json.loads((module(slug) / "module.json").read_text(encoding="utf-8")).get(key, [])


def main():
    tmp = Path(tempfile.mkdtemp(prefix="modkit-test-"))
    try:
        # ---- 1. skin-manager ---------------------------------------------
        work = tmp / "skin" / "unpacked"
        cjs = make_tree(work)
        cycle("skin", "skin-manager", work, None)

        # ---- 2. account-switcher (LF) ------------------------------------
        work = tmp / "acct-lf" / "unpacked"
        cjs = make_tree(work, main=MOCK_MAIN_LF)
        cycle("account(LF)", "account-switcher", work, None)

        # ---- 3. account-switcher (CRLF) -----------------------------------
        work = tmp / "acct-crlf" / "unpacked"
        cjs = make_tree(work, main=MOCK_MAIN_CRLF)
        cycle("account(CRLF)", "account-switcher", work, None)

        # ---- 4. route-override: legacy line replace + config migration ----
        work = tmp / "route" / "unpacked"
        cjs = make_tree(work)
        env = dict(os.environ)
        env["USERPROFILE"] = str(tmp / "home")
        cjs.write_bytes(MOCK_CJS[:MOCK_CJS.index(b'\n"use strict";') + len(b'\n"use strict";')]
                        + LEGACY_RO_LINE + b"\n" + MOCK_CJS[MOCK_CJS.index(b'\n"use strict";') + len(b'\n"use strict";'):])
        legacy_dir = Path("C:/old/zcode-route-override")
        legacy_dir.mkdir(parents=True, exist_ok=True)
        (legacy_dir / "route-overrides.json").write_text(
            '{"routes":[{"match":"x.example.com"}]}', encoding="utf-8")
        try:
            rc, out = run(module("route-override") / "inject.py",
                          ["--dir", str(work), "--zcode-cjs", str(cjs)], env)
            check("route: inject over legacy line", rc == 0, out[-500:])
            data = cjs.read_bytes()
            check("route: exactly one /*zro*/", data.count(b"/*zro*/") == 1)
            check("route: new line points at runtime dir",
                  b".zcode/plugins/route-override/wrapper.js" in data)
            rt = Path(env["USERPROFILE"]) / ".zcode" / "plugins" / "route-override"
            check("route: config migrated to runtime dir",
                  (rt / "route-overrides.json").exists())
            check("route: token generated at runtime dir",
                  (rt / "auth-token").exists())
            # token must not be the stale static one
            tok = (rt / "auth-token").read_text(encoding="utf-8").strip()
            check("route: token is fresh hex64", len(tok) == 64 and all(
                c in "0123456789abcdef" for c in tok))
            rc2, _ = run(module("route-override") / "verify.py",
                         ["--dir", str(work), "--zcode-cjs", str(cjs)], env)
            check("route: verify after legacy replace", rc2 == 0)
            # uninject removes the (replaced) line: file must end fully clean
            run(module("route-override") / "uninject.py",
                ["--dir", str(work), "--zcode-cjs", str(cjs)], env)
            check("route: cjs restored after uninject", cjs.read_bytes() == MOCK_CJS)
        finally:
            shutil.rmtree(legacy_dir, ignore_errors=True)
            cjs.write_bytes(MOCK_CJS)

        # ---- 5. pin + route together: order matters -----------------------
        work = tmp / "pinroute" / "unpacked"
        cjs = make_tree(work)
        env = dict(os.environ)
        env["USERPROFILE"] = str(tmp / "home2")
        rc, out = run(module("route-override") / "inject.py",
                      ["--dir", str(work), "--zcode-cjs", str(cjs)], env)
        check("combo: route inject first", rc == 0, out[-300:])
        rc, out = run(module("pin") / "inject.py",
                      ["--dir", str(work), "--zcode-cjs", str(cjs)], env)
        check("combo: pin inject second", rc == 0, out[-300:])
        data = cjs.read_bytes()
        i_ro = data.find(b"/*zro*/")
        i_pin = data.find(b"/*zpin*/")
        check("combo: pin wraps outside route (pin after zro)", 0 < i_ro < i_pin)
        check("combo: pin require points at runtime dir",
              b".zcode/plugins/pin/pin-wrapper.js" in data)
        check("combo: pin token in runtime dir",
              (Path(env["USERPROFILE"]) / ".zcode/plugins/pin/auth-token").exists())
        check("combo: pin-core.js deployed with wrapper",
              (Path(env["USERPROFILE"]) / ".zcode/plugins/pin/pin-core.js").exists())
        rc, _ = run(module("pin") / "verify.py",
                    ["--dir", str(work), "--zcode-cjs", str(cjs)], env)
        check("combo: pin verify", rc == 0)
        rc, _ = run(module("route-override") / "verify.py",
                    ["--dir", str(work), "--zcode-cjs", str(cjs)], env)
        check("combo: route verify", rc == 0)
        # UI token placeholder replaced
        html = (work / "out" / "renderer" / "index.html").read_text(encoding="utf-8")
        check("combo: pin token placeholder replaced",
              "__ZPIN_TOKEN__" not in html)
        check("combo: route token embedded", "ZRO_TOKEN" in html)
        # restore cjs exactly: uninject pin then route
        run(module("pin") / "uninject.py",
            ["--dir", str(work), "--zcode-cjs", str(cjs)], env)
        run(module("route-override") / "uninject.py",
            ["--dir", str(work), "--zcode-cjs", str(cjs)], env)
        check("combo: cjs byte-identical after both uninjects",
              cjs.read_bytes() == MOCK_CJS)

        # ---- 6. pin standalone (no route marker): fallback anchor ---------
        work = tmp / "pin-solo" / "unpacked"
        cjs = make_tree(work)
        env["USERPROFILE"] = str(tmp / "home3")
        rc, out = run(module("pin") / "inject.py",
                      ["--dir", str(work), "--zcode-cjs", str(cjs)], env)
        check("pin-solo: inject with fallback anchor", rc == 0, out[-300:])
        rc, _ = run(module("pin") / "verify.py",
                    ["--dir", str(work), "--zcode-cjs", str(cjs)], env)
        check("pin-solo: verify", rc == 0)
        run(module("pin") / "uninject.py",
            ["--dir", str(work), "--zcode-cjs", str(cjs)], env)
        check("pin-solo: cjs restored", cjs.read_bytes() == MOCK_CJS)

        # ---- 7. pin legacy line replace ------------------------------------
        work = tmp / "pin-legacy" / "unpacked"
        cjs = make_tree(work)
        cjs.write_bytes(MOCK_CJS[:MOCK_CJS.index(b'\n"use strict";') + len(b'\n"use strict";')]
                        + LEGACY_PIN_LINE + b"\n" + MOCK_CJS[MOCK_CJS.index(b'\n"use strict";') + len(b'\n"use strict";'):])
        rc, out = run(module("pin") / "inject.py",
                      ["--dir", str(work), "--zcode-cjs", str(cjs)], env)
        check("pin-legacy: replaced old line", rc == 0 and cjs.read_bytes().count(b"/*zpin*/") == 1,
              out[-300:])
        run(module("pin") / "uninject.py",
            ["--dir", str(work), "--zcode-cjs", str(cjs)], env)
        # the legacy line was replaced by inject and removed by uninject:
        # the file must end up fully clean (no pin line at all)
        check("pin-legacy: restored clean", cjs.read_bytes() == MOCK_CJS)

        # ---- 8. snapshot-kill ----------------------------------------------
        work = tmp / "snap" / "unpacked"
        cjs = make_tree(work)
        cycle("snapshot-kill", "snapshot-kill", work, None)

        # ---- 9. usage-bar ---------------------------------------------------
        work = tmp / "usage" / "unpacked"
        cjs = make_tree(work)
        cycle("usage-bar", "usage-bar", work, None)
        # config seeded with a WORKING python_path (not the example placeholder)
        seed_cfg = Path(tmp) / "usage-home-dummy"  # actual home is work.parent/"home"
        # cycle() isolates USERPROFILE to tmp/<case>/home; usage-bar case home:
        usage_home = tmp / "usage" / "home"
        seeded = usage_home / ".zcode" / "plugins" / "usage-bar" / "config.json"
        if seeded.exists():
            import json as _json
            v = _json.loads(seeded.read_text(encoding="utf-8")).get("python_path", "")
            check("usage-bar: config python_path seeded real", v and "path\\to" not in v, v)
        else:
            check("usage-bar: config python_path seeded real", False, "no config.json")

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n===== {PASS} passed, {FAIL} failed =====")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()

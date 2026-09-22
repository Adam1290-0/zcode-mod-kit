#!/usr/bin/env python3
"""Edge-case and failure-path tests for the 6 mod-kit modules.

Complements test_modules.py (happy-path round-trip). Here we exercise
branches the happy path never touches:
  - injectors abort with exit != 0 when required files are missing
  - snapshot-kill [NOT-NEEDED] path on a build where the subsystem is absent
  - snapshot-kill refuses when an anchor matches more than once (exit 2)
  - route-override refuses to stack a second /*zro*/ line on a corrupt form (exit 1)
  - verify.py returns non-zero on a never-injected tree (for every module)
  - uninject.py is a no-op SKIP (exit 0) on a never-injected tree
  - 4 modules all injecting into the SAME index.html, then reverse-order
    uninject, byte-identical restoration (marker-collision safety)

Style follows test_modules.py: check(name, cond, detail), subprocess, tempdir,
USERPROFILE isolation. Does NOT import or modify module code.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
MODULES = KIT / "modules"

# --- same fixtures as test_modules.py, plus subsystem-free host variant ------
MOCK_HTML = ("<!doctype html><html><head><title>t</title></head>"
             "<body><div id=root></div></body></html>\n")
MOCK_MAIN_LF = '"use strict";\nfunction boot(){console.log(1)}\n'
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
# Same as MOCK_HOST but neither SUBSYSTEM_KEYS string appears: models a build
# where the snapshot subsystem was removed upstream.
MOCK_HOST_NO_SNAPSHOT = (
    '"use strict";\n'
    "class Foo {\n"
    "  async doSomething(t){return 1;}\n"
    "  async doOther(t){return 2;}\n"
    "}\n"
    "function x(){;a(pIe,\"removeGeneratedArtifactFiles\");var Bk=class{}}\n"
)
# One of the two snapshot anchors appears TWICE: anchor-count-mismatch branch.
MOCK_HOST_ANCHOR_DUP = (
    '"use strict";\n'
    "class Foo {\n"
    "  async captureBeforePromptUnsafe(t){t.signal?.throwIfAborted();"
    "let r=await this.tokenProvider();return 1;}\n"
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
# A /*zro*/ marker with no matching try{require(... form within 400 bytes:
# models a hand-edited / stale line. inject.py must refuse to stack.
CORRUPT_ZRO_CJS = (b'#!/usr/bin/env node\n"use strict";\n'
                   b'// stale line, no matching try{require\n'
                   b'/*zro*/\nconsole.log("boot");\n')

# All 6 module slugs, and which ones also touch zcode.cjs.
ALL_SLUGS = ["account-switcher", "pin", "route-override",
             "skin-manager", "snapshot-kill", "usage-bar"]
CJS_SLUGS = {"pin", "route-override"}

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        detail_s = (" " + str(detail)) if detail else ""
        print(f"  [FAIL] {name}{detail_s}")


def run(script, args, env):
    proc = subprocess.run([sys.executable, str(script)] + args,
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env)
    return proc.returncode, proc.stdout + proc.stderr


def module(slug):
    return MODULES / slug


def targets(slug):
    return json.loads((module(slug) / "module.json").read_text(encoding="utf-8")).get("targets", [])


def env_for(work):
    env = dict(os.environ)
    env["USERPROFILE"] = str(work.parent / "home")
    env["HOME"] = str(work.parent / "home")
    return env


def make_tree(root, html=MOCK_HTML, main=MOCK_MAIN_LF, cjs=MOCK_CJS, host=MOCK_HOST):
    (root / "out" / "renderer").mkdir(parents=True, exist_ok=True)
    (root / "out" / "main").mkdir(parents=True, exist_ok=True)
    (root / "out" / "host").mkdir(parents=True, exist_ok=True)
    (root / "out" / "renderer" / "index.html").write_text(html, encoding="utf-8")
    (root / "out" / "main" / "index.js").write_text(main, encoding="utf-8", newline="")
    (root / "out" / "host" / "index.js").write_text(host, encoding="utf-8")
    cjs_p = root.parent / "zcode.cjs"
    cjs_p.write_bytes(cjs)
    return cjs_p


# =============================================================================
# Test 1: every injector exits non-zero when a required file is missing
# =============================================================================
def test_missing_targets():
    print("\n--- Test 1: injectors abort on missing required files ---")
    tmp = Path(tempfile.mkdtemp(prefix="modkit-edge1-"))
    try:
        # account-switcher: no out/main/index.js
        w = tmp / "acct" / "unpacked"
        (w / "out" / "renderer").mkdir(parents=True)
        (w / "out" / "renderer" / "index.html").write_text(MOCK_HTML, encoding="utf-8")
        env = env_for(w)
        rc, out = run(module("account-switcher") / "inject.py",
                      ["--dir", str(w)], env)
        check("account: missing out/main/index.js -> exit 1", rc != 0, f"rc={rc}")
        check("account: error message names the file",
              "required file missing" in out, out[-200:])

        # usage-bar: no out/main/index.js
        w = tmp / "usage" / "unpacked"
        (w / "out" / "renderer").mkdir(parents=True)
        env = env_for(w)
        rc, out = run(module("usage-bar") / "inject.py",
                      ["--dir", str(w)], env)
        check("usage-bar: missing out/main/index.js -> exit 1", rc != 0, f"rc={rc}")

        # skin-manager: no index.html
        w = tmp / "skin" / "unpacked"
        (w / "out" / "main").mkdir(parents=True)
        env = env_for(w)
        rc, out = run(module("skin-manager") / "inject.py",
                      ["--dir", str(w)], env)
        check("skin: missing index.html -> exit 1", rc != 0, f"rc={rc}")

        # snapshot-kill: no out/host/index.js
        w = tmp / "snap" / "unpacked"
        (w / "out" / "main").mkdir(parents=True)
        env = env_for(w)
        rc, out = run(module("snapshot-kill") / "inject.py",
                      ["--dir", str(w)], env)
        check("snapshot-kill: missing out/host/index.js -> exit 1", rc != 0, f"rc={rc}")

        # route-override: --dir doesn't exist at all
        env = dict(os.environ)
        rc, out = run(module("route-override") / "inject.py",
                      ["--dir", str(tmp / "nonexistent")], env)
        check("route: nonexistent --dir -> exit 1", rc != 0, f"rc={rc}")

        # pin: no index.html (inject_ui returns False -> main returns 1)
        w = tmp / "pin" / "unpacked"
        (w / "out" / "main").mkdir(parents=True)
        (w / "out" / "main" / "index.js").write_text(MOCK_MAIN_LF, encoding="utf-8", newline="")
        env = env_for(w)
        rc, out = run(module("pin") / "inject.py",
                      ["--dir", str(w)], env)
        check("pin: missing index.html -> exit 1", rc != 0, f"rc={rc}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# =============================================================================
# Test 2: snapshot-kill [NOT-NEEDED] on a build with no snapshot subsystem
# =============================================================================
def test_snapshot_not_needed():
    print("\n--- Test 2: snapshot-kill [NOT-NEEDED] on subsystem-absent build ---")
    tmp = Path(tempfile.mkdtemp(prefix="modkit-edge2-"))
    try:
        w = tmp / "snap" / "unpacked"
        cjs = make_tree(w, host=MOCK_HOST_NO_SNAPSHOT)
        env = env_for(w)
        html_path = w / "out" / "host" / "index.js"
        before = html_path.read_bytes()

        # inject: should print [NOT-NEEDED] and exit 0, file unchanged
        rc, out = run(module("snapshot-kill") / "inject.py",
                      ["--dir", str(w)], env)
        check("snap[NOT-NEEDED]: inject exit 0", rc == 0, out[-300:])
        check("snap[NOT-NEEDED]: prints [NOT-NEEDED] tag",
              "[NOT-NEEDED]" in out, out[-300:])
        check("snap[NOT-NEEDED]: file untouched",
              html_path.read_bytes() == before)

        # verify: also reports [NOT-NEEDED] and exits 0 (safe state)
        rc, out = run(module("snapshot-kill") / "verify.py",
                      ["--dir", str(w)], env)
        check("snap[NOT-NEEDED]: verify exit 0", rc == 0, out[-300:])
        check("snap[NOT-NEEDED]: verify prints [NOT-NEEDED]",
              "[NOT-NEEDED]" in out, out[-300:])

        # uninject: also a clean no-op with [NOT-NEEDED]
        rc, out = run(module("snapshot-kill") / "uninject.py",
                      ["--dir", str(w)], env)
        check("snap[NOT-NEEDED]: uninject exit 0", rc == 0, out[-300:])
        check("snap[NOT-NEEDED]: uninject prints [NOT-NEEDED]",
              "[NOT-NEEDED]" in out, out[-300:])
        check("snap[NOT-NEEDED]: file still untouched",
              html_path.read_bytes() == before)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# =============================================================================
# Test 3: snapshot-kill refuses when an anchor matches more than once
# =============================================================================
def test_snapshot_anchor_dup():
    print("\n--- Test 3: snapshot-kill refuses on duplicate anchor (exit 2) ---")
    tmp = Path(tempfile.mkdtemp(prefix="modkit-edge3-"))
    try:
        w = tmp / "snap" / "unpacked"
        cjs = make_tree(w, host=MOCK_HOST_ANCHOR_DUP)
        env = env_for(w)
        host_path = w / "out" / "host" / "index.js"
        before = host_path.read_bytes()

        rc, out = run(module("snapshot-kill") / "inject.py",
                      ["--dir", str(w)], env)
        check("snap[anchor-dup]: inject exit 2", rc == 2, f"rc={rc}")
        check("snap[anchor-dup]: error names the duplicate anchor",
              "matched 2 times" in out, out[-300:])
        check("snap[anchor-dup]: file untouched (refused to inject)",
              host_path.read_bytes() == before)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# =============================================================================
# Test 4: route-override refuses to stack on a corrupt /*zro*/ form (exit 1)
# =============================================================================
def test_route_corrupt_marker():
    print("\n--- Test 4: route-override refuses on unknown-form /*zro*/ (exit 1) ---")
    tmp = Path(tempfile.mkdtemp(prefix="modkit-edge4-"))
    try:
        w = tmp / "route" / "unpacked"
        cjs = make_tree(w)
        cjs.write_bytes(CORRUPT_ZRO_CJS)
        env = env_for(w)
        before = cjs.read_bytes()

        rc, out = run(module("route-override") / "inject.py",
                      ["--dir", str(w), "--zcode-cjs", str(cjs)], env)
        check("route[corrupt]: inject exit 1", rc != 0, f"rc={rc}")
        check("route[corrupt]: error says refusing to stack",
              "refusing to stack" in out, out[-400:])
        check("route[corrupt]: cjs untouched", cjs.read_bytes() == before)
        # The renderer block should NOT have been written either (inject aborts
        # before reaching the renderer step).
        html = (w / "out" / "renderer" / "index.html").read_text(encoding="utf-8")
        check("route[corrupt]: renderer untouched",
              "zcode-route-override-ui" not in html)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# =============================================================================
# Test 5: every verify.py returns non-zero on a never-injected tree
# =============================================================================
def test_verify_never_injected():
    print("\n--- Test 5: verify.py non-zero on a never-injected tree ---")
    tmp = Path(tempfile.mkdtemp(prefix="modkit-edge5-"))
    try:
        w = tmp / "tree" / "unpacked"
        cjs = make_tree(w)
        env = env_for(w)

        for slug in ALL_SLUGS:
            args = ["--dir", str(w)]
            if slug in CJS_SLUGS:
                args += ["--zcode-cjs", str(cjs)]
            rc, out = run(module(slug) / "verify.py", args, env)
            # NOTE: snapshot-kill verify returns 0 when the subsystem IS present
            # (MOCK_HOST has it) but the marker is absent -> exit 1. Confirmed.
            check(f"verify[{slug}] never-injected -> exit 1", rc != 0,
                  f"rc={rc} out={out[-200:]}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# =============================================================================
# Test 6: every uninject.py is a clean SKIP (exit 0) on a never-injected tree
# =============================================================================
def test_uninject_never_injected():
    print("\n--- Test 6: uninject.py no-op SKIP on a never-injected tree ---")
    tmp = Path(tempfile.mkdtemp(prefix="modkit-edge6-"))
    try:
        w = tmp / "tree" / "unpacked"
        cjs = make_tree(w)
        env = env_for(w)
        snap = {p: p.read_bytes() for p in w.rglob("*") if p.is_file()}
        snap[cjs] = cjs.read_bytes()

        for slug in ALL_SLUGS:
            args = ["--dir", str(w)]
            if slug in CJS_SLUGS:
                args += ["--zcode-cjs", str(cjs)]
            rc, out = run(module(slug) / "uninject.py", args, env)
            check(f"uninject[{slug}] never-injected -> exit 0", rc == 0,
                  f"rc={rc} out={out[-200:]}")

        # nothing on disk should have changed
        bad = []
        for p, b in snap.items():
            if p.exists() and p.read_bytes() != b:
                bad.append(str(p))
            elif not p.exists():
                bad.append(str(p) + " (deleted)")
        check("uninject[all]: tree byte-identical after 6 no-op uninjects",
              not bad, "; ".join(bad[:4]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# =============================================================================
# Test 7: 4 modules all inject into the SAME index.html; reverse-order
# uninject restores bytes exactly.
# =============================================================================
def test_combined_html_collision():
    print("\n--- Test 7: 4 modules share index.html; reverse-order uninject ---")
    tmp = Path(tempfile.mkdtemp(prefix="modkit-edge7-"))
    try:
        w = tmp / "combo" / "unpacked"
        cjs = make_tree(w)
        env = env_for(w)
        html_path = w / "out" / "renderer" / "index.html"
        original_html = html_path.read_bytes()
        original_cjs = cjs.read_bytes()

        # inject order: skin -> route -> pin -> account (each adds a <script>
        # block before </body>; account also prepends a main import line)
        order = ["skin-manager", "route-override", "pin", "account-switcher"]
        for slug in order:
            args = ["--dir", str(w)]
            if slug in CJS_SLUGS:
                args += ["--zcode-cjs", str(cjs)]
            rc, out = run(module(slug) / "inject.py", args, env)
            check(f"combo: {slug} inject exit 0", rc == 0, out[-300:])

        html = html_path.read_text(encoding="utf-8")
        markers = ['zcode-skin-ui', 'zcode-route-override-ui',
                   'zcode-pin-ui', 'zcode-account-switcher']
        for m in markers:
            check(f"combo: marker {m} present", m in html)
        check("combo: all 4 blocks present",
              all(m in html for m in markers))
        # exactly one </body> remains (no block ate it)
        check("combo: exactly one </body>", html.count("</body>") == 1)

        # reverse-order uninject: account -> pin -> route -> skin
        for slug in reversed(order):
            args = ["--dir", str(w)]
            if slug in CJS_SLUGS:
                args += ["--zcode-cjs", str(cjs)]
            rc, out = run(module(slug) / "uninject.py", args, env)
            check(f"combo: {slug} uninject exit 0", rc == 0, out[-300:])

        check("combo: index.html byte-identical after all 4 uninjects",
              html_path.read_bytes() == original_html,
              "diff: " + repr(html_path.read_bytes()[:200]))
        check("combo: zcode.cjs byte-identical",
              cjs.read_bytes() == original_cjs)
        # account also prepends a line to out/main/index.js; must be gone too
        main_path = w / "out" / "main" / "index.js"
        check("combo: out/main/index.js restored (no leftover import)",
              main_path.read_text(encoding="utf-8", newline="") == MOCK_MAIN_LF)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# =============================================================================
def main():
    test_missing_targets()
    test_snapshot_not_needed()
    test_snapshot_anchor_dup()
    test_route_corrupt_marker()
    test_verify_never_injected()
    test_uninject_never_injected()
    test_combined_html_collision()

    print(f"\n===== {PASS} passed, {FAIL} failed =====")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()

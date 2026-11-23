#!/usr/bin/env python3
"""Engine-level regression tests for modkit.asar_is_clean / read_asar_version.

Locks in the 2026-09-22 data-loss class: a PARTIALLY patched asar must never
read as 'clean', otherwise the kitbak refresh overwrites the clean baseline
with a patched asar. The module-level asar_is_clean is exercised directly
against synthetic asars built to match modkit's header parser.

Run: python tests/test_engine.py
"""
import json
import shutil
import struct
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import modkit as M  # noqa: E402

_passed = 0
_failed = 0


def check(name, cond, detail=""):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  [PASS] {name}")
    else:
        _failed += 1
        print(f"  [FAIL] {name}  {detail}")


def build_asar(entries):
    """Minimal asar matching modkit's parser:
    u32(4) + u32(header_len) + header(JSON, 4-aligned) + body.
    entries: {"relative/path": bytes}. Files carry size + string offset."""
    files, body, off = {}, b"", 0
    for rel in sorted(entries):
        data = entries[rel]
        node = files
        parts = rel.split("/")
        for part in parts[:-1]:
            node = node.setdefault(part, {"files": {}})["files"]
        node[parts[-1]] = {"size": len(data), "offset": str(off)}
        body += data
        off += len(data)
    hdr = json.dumps({"files": files}, separators=(",", ":")).encode()
    hdr += b"\x00" * ((4 - (8 + len(hdr)) % 4) % 4)  # align body start to 4
    return struct.pack("<I", 4) + struct.pack("<I", len(hdr)) + hdr + body


PKG = b'{"name":"zcode","version":"3.14.1"}'
CLEAN_HTML = b"<!doctype html><html><body><div id=root></div></body></html>"


def write_asar(tmp, name, entries):
    p = tmp / name
    p.write_bytes(build_asar(entries))
    return p


def main():
    print("--- modkit engine: read_asar_version + asar_is_clean ---")
    tmp = Path(tempfile.mkdtemp(prefix="modkit-engine-"))
    try:
        # version read through the header
        p = write_asar(tmp, "v.asar", {"package.json": PKG,
                                       "out/renderer/index.html": CLEAN_HTML})
        check("read_asar_version -> 3.14.1", M.read_asar_version(p) == "3.14.1")

        # pristine asar -> clean
        p = write_asar(tmp, "clean.asar", {"package.json": PKG,
                                           "out/renderer/index.html": CLEAN_HTML})
        check("asar_is_clean: pristine -> True", M.asar_is_clean(p) is True)

        # each renderer module marker -> NOT clean (the incident regression:
        # pin/route-only installs used to read as clean and clobbered kitbak)
        for marker in (b"zcode-skin-ui", b"zcode-account-switcher",
                       b"zcode-route-override-ui", b"zcode-pin-ui",
                       b"zcode-voice-ui"):
            html = b"<body><script id='" + marker + b"'></script></body>"
            p = write_asar(tmp, "r.asar", {"package.json": PKG,
                                           "out/renderer/index.html": html})
            check(f"asar_is_clean: {marker.decode()} -> not clean",
                  M.asar_is_clean(p) is False)

        # snapshot-kill lives in out/host/index.js
        p = write_asar(tmp, "host.asar", {
            "package.json": PKG,
            "out/renderer/index.html": CLEAN_HTML,
            "out/host/index.js": b"/*[zcode-snapshot-kill-switch]*/x"})
        check("asar_is_clean: snapshot host marker -> not clean",
              M.asar_is_clean(p) is False)

        # usage-bar lives in out/main/index.js ([zusage] tag)
        p = write_asar(tmp, "main.asar", {
            "package.json": PKG,
            "out/renderer/index.html": CLEAN_HTML,
            "out/main/index.js": b'import("x");console.error("[zusage] load failed")'})
        check("asar_is_clean: usage-bar main marker -> not clean",
              M.asar_is_clean(p) is False)

        # voice-input appends its own dynamic-import line to the SAME file.
        # Missing this marker made a voice-only install read as clean and
        # refresh kitbak on top of a patched asar.
        p = write_asar(tmp, "vmain.asar", {
            "package.json": PKG,
            "out/renderer/index.html": CLEAN_HTML,
            "out/main/index.js": b'import("x/voice-main.cjs");'})
        check("asar_is_clean: voice-input main marker -> not clean",
              M.asar_is_clean(p) is False)

        # edit-resend lives in a content-hashed renderer/assets chunk
        big = b"x" * 100_000 + b"/*[zcode-editresend-ui]*/"
        p = write_asar(tmp, "chunk.asar", {
            "package.json": PKG,
            "out/renderer/index.html": CLEAN_HTML,
            "out/renderer/assets/index-CSpM3qgc.js": big})
        check("asar_is_clean: edit-resend chunk marker -> not clean",
              M.asar_is_clean(p) is False)

        # fail-closed: even a sub-100KB js carrying the marker counts as patched
        p = write_asar(tmp, "small.asar", {
            "package.json": PKG,
            "out/renderer/index.html": CLEAN_HTML,
            "out/renderer/assets/tiny.js": b"/*[zcode-editresend-ui]*/"})
        check("asar_is_clean: small js with chunk marker -> not clean",
              M.asar_is_clean(p) is False)

        # unreadable / garbage -> False (fail-closed, never destroy the backup)
        for i, bad in enumerate((b"", b"\x00" * 16, b"garbage-not-an-asar")):
            p = tmp / f"bad{i}.asar"
            p.write_bytes(bad)
            check(f"asar_is_clean: unreadable#{i} -> False (fail-closed)",
                  M.asar_is_clean(p) is False)
        gp = tmp / "bad0.asar"
        check("read_asar_version: garbage -> None",
              M.read_asar_version(gp) is None)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # ---- install-location discovery (2026-09-24 portability fix) ----
    # The old code only looked at H:/Zcode - the kit must find ZCode wherever
    # it is installed, and must NOT silently fall back to the kit folder.
    print("--- modkit engine: find_zcode_root ---")
    t2 = Path(tempfile.mkdtemp(prefix="modkit-root-"))
    try:
        check("find_root: empty dir is not a root",
              M._is_zcode_root(t2) is False)
        fake = t2 / "ZCode"
        (fake / "resources").mkdir(parents=True)
        (fake / "resources" / "app.asar").write_bytes(b"x")
        check("find_root: dir with resources/app.asar is a root",
              M._is_zcode_root(fake) is True)

        # ZCODE_ROOT override must win over everything else on this machine
        import os as _os
        old = _os.environ.get("ZCODE_ROOT")
        try:
            _os.environ["ZCODE_ROOT"] = str(fake)
            check("find_root: ZCODE_ROOT override wins",
                  M.find_zcode_root() == fake)
            # a bad override must NOT silently pick another machine's install
            _os.environ["ZCODE_ROOT"] = str(t2 / "no-such-dir")
            found = M.find_zcode_root()
            check("find_root: bad override does not return unrelated paths",
                  found is None or not str(found).startswith(str(t2 / "no-such-dir")))
        finally:
            if old is None:
                _os.environ.pop("ZCODE_ROOT", None)
            else:
                _os.environ["ZCODE_ROOT"] = old

        # with no override, discovery must at least not crash and return a
        # root (or None) - never the kit folder itself unless it IS the root
        no_env = M.find_zcode_root()
        check("find_root: no-crash on plain discovery", True,
              f"returned={no_env}")
        if no_env is not None:
            check("find_root: returned root carries an asar",
                  M._is_zcode_root(no_env))
    finally:
        shutil.rmtree(t2, ignore_errors=True)

    # ---- apply confirmation gate -------------------------------------------
    # ENTER must never start a 2-3 minute rewrite of a 385 MB app on one
    # keystroke: the plan is printed and an explicit y is required.
    print("\n--- confirm_plan: ENTER now needs an explicit yes")
    mods = [{"slug": "pin", "version": "1.0.8", "display_name": "Pin"},
            {"slug": "voice-input", "version": "1.2.0", "display_name": "Voice"}]
    sel = {"pin": True, "voice-input": False}
    import builtins
    import io as _io

    def with_answer(ans, selection=None):
        old_in = builtins.input
        old_out = sys.stdout
        buf = _io.StringIO()
        sys.stdout = buf
        builtins.input = lambda *a, **k: ans
        try:
            return M.confirm_plan(mods, selection or sel), buf.getvalue()
        finally:
            builtins.input = old_in
            sys.stdout = old_out

    ok_y, out_y = with_answer("y")
    check("confirm_plan: 'y' proceeds", ok_y is True)
    check("confirm_plan: plan lists every module",
          out_y.count("[+]") == 1 and out_y.count("[ ]") == 1, out_y[-300:])
    ok_n, _ = with_answer("n")
    check("confirm_plan: 'n' declines", ok_n is False)
    ok_blank, _ = with_answer("")
    check("confirm_plan: blank answer declines (safe default)", ok_blank is False)
    ok_junk, _ = with_answer("yes please")
    check("confirm_plan: unrecognised answer declines", ok_junk is False)
    ok_yes, _ = with_answer("YES")
    check("confirm_plan: answer is case-insensitive", ok_yes is True)

    # all-OFF must say out loud that it REMOVES
    _, out_off = with_answer("n", {"pin": False, "voice-input": False})
    check("confirm_plan: all-OFF warns that it removes everything",
          "REMOVE" in out_off, out_off[-300:])

    # ---- menu label falls back when the console cannot encode Chinese ------
    # sys.stdout.encoding is read-only on a real stream, so swap in a stub.
    cyr = {"slug": "pin", "version": "1.0.8", "display_name": "上下文固定 Pin"}

    class _Enc:
        def __init__(self, enc):
            self.encoding = enc

        def write(self, *_):
            pass

        def flush(self):
            pass

    real_out = sys.stdout
    try:
        # display_name() now depends on the active language, so pin it: in
        # English mode the Chinese name is deliberately not used.
        M.set_lang("zh")
        sys.stdout = _Enc("ascii")
        check("display_name: falls back to an ASCII label on an ascii console",
              M.display_name(cyr).isascii(), M.display_name(cyr))
        sys.stdout = _Enc("utf-8")
        check("display_name: uses the Chinese name on a utf-8 console",
              M.display_name(cyr) == "上下文固定 Pin", M.display_name(cyr))
        M.set_lang("en")
        check("display_name: English mode uses the ASCII label even on utf-8",
              M.display_name(cyr).isascii(), M.display_name(cyr))
    finally:
        sys.stdout = real_out
        M.set_lang("en")
    check("display_name: unknown slug still gets a label",
          bool(M.display_name({"slug": "no-such", "version": "1"})),
          "empty name")

    # ---- i18n: locale default + live switch ---------------------------------
    print("\n--- i18n: Chinese systems default to Chinese, L switches")
    saved = {k: _os.environ.get(k) for k in ("LANG", "LC_ALL", "LANGUAGE")}
    try:
        for k in saved:
            _os.environ.pop(k, None)
        # A real locale string wins (Windows UI language is the fallback, and
        # on the test machine that is unknowable from here).
        _os.environ["LANG"] = "zh_CN.UTF-8"
        check("lang: zh_CN locale -> zh", M._system_lang() == "zh",
              M._system_lang())
        _os.environ["LANG"] = "en_US.UTF-8"
        check("lang: en_US locale -> en", M._system_lang() == "en",
              M._system_lang())
        # Git Bash on a Chinese Windows sets C.UTF-8; it must NOT force English
        # (that was a real bug: every Chinese machine came out English).
        _os.environ["LANG"] = "C.UTF-8"
        got = M._system_lang()
        check("lang: C.UTF-8 is ignored, not treated as English",
              got in ("zh", "en"), got)
        if _os.name == "nt":
            import ctypes
            lid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            want = "zh" if (lid & 0xFF) == 0x04 else "en"
            check("lang: C.UTF-8 falls through to the Windows UI language",
                  got == want, "%s vs %s" % (got, want))
    finally:
        for k, v in saved.items():
            if v is None:
                _os.environ.pop(k, None)
            else:
                _os.environ[k] = v

    M.set_lang("en")
    check("lang: set_lang('en')", M.lang() == "en")
    M.set_lang("zh")
    check("lang: set_lang('zh')", M.lang() == "zh")
    M.set_lang("klingon")
    check("lang: unknown language falls back to en", M.lang() == "en")

    M.set_lang("zh")
    check("i18n: Chinese menu hint is Chinese",
          "上下键" in M.t("menu.hint1"), M.t("menu.hint1"))
    M.set_lang("en")
    check("i18n: English menu hint is English",
          "UP/DOWN" in M.t("menu.hint1"), M.t("menu.hint1"))

    # Every key must exist in both languages, or the menu silently reverts to
    # English mid-screen on a Chinese system.
    missing = [(k, l) for k, v in M.T.items() for l in M.LANGS
               if not v.get(l)]
    check("i18n: every string has both translations", not missing, str(missing[:4]))
    # Placeholders must match across languages or % formatting throws.
    bad = []
    for k, v in M.T.items():
        n_en = v.get("en", "").count("%")
        for l in M.LANGS:
            if v.get(l, "").count("%") != n_en:
                bad.append((k, l))
    check("i18n: placeholder counts agree across languages", not bad, str(bad[:4]))

    # ---- intro animation: must actually run, in both languages ------------
    # The snowfall loop used a local `t = f / fps` that shadowed the global
    # translation helper t(), so the very first frame raised UnboundLocalError
    # and the intro died before printing anything. Nothing tested this path.
    print("\n--- intro: snowfall + splash plate render cleanly")
    import io as _io2

    class _TTY(_io2.StringIO):
        def isatty(self):
            return True
        encoding = "utf-8"

    for lg in ("zh", "en"):
        buf = _TTY()
        old = sys.stdout
        sys.stdout = buf
        try:
            M.set_lang(lg)
            M.snowfall(seconds=0.4, rows=12, cols=70, fps=20)
            M.clear()
            print(M.splash_plate(M.load_modules(), M.KIT_VERSION))
        finally:
            out = buf.getvalue()
            sys.stdout = old
        check("intro[%s]: no traceback text in the output" % lg,
              "Traceback" not in out and "UnboundLocal" not in out
              and "TypeError" not in out, out[-300:])
        check("intro[%s]: emitted animation frames" % lg,
              out.count("\x1b[H") > 3, "frames=%d" % out.count("\x1b[H"))
        check("intro[%s]: alternate screen paired" % lg,
              out.count("\x1b[?1049h") == out.count("\x1b[?1049l"))
        check("intro[%s]: skip hint shown" % lg,
              ("按任意键" in out) or ("press any key" in out))
        check("intro[%s]: splash plate rendered" % lg,
              "zcode mod kit" in out, out[-200:])
    M.set_lang("en")

    # The translation helper must stay callable from inside snowfall: a local
    # assignment to the same name would shadow it again.
    import ast as _ast
    src = (ROOT / "modkit.py").read_text(encoding="utf-8")
    tree = _ast.parse(src)
    shadowed = []
    for n in _ast.walk(tree):
        if isinstance(n, _ast.FunctionDef):
            for x in _ast.walk(n):
                if (isinstance(x, _ast.Name) and isinstance(x.ctx, _ast.Store)
                        and x.id == "t"):
                    shadowed.append(n.name)
    check("intro: no function rebinds the global t() helper",
          not shadowed, str(shadowed))

    print(f"\n===== {_passed} passed, {_failed} failed =====")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())

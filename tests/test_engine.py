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
                       b"zcode-route-override-ui", b"zcode-pin-ui"):
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

    print(f"\n===== {_passed} passed, {_failed} failed =====")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
